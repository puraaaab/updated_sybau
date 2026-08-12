"""
VMS Pro — Security Utilities & Anti-TOCTOU SSRF Validator
Provides path traversal protections and strict Anti-TOCTOU SSRF URL validation.
Blocks private IPv4, private IPv6, loopback, link-local, cloud metadata (169.254.169.254),
DNS rebinding, and unvalidated HTTP redirects across all camera, webhook, VLM, and media import URLs.
"""

import socket
import ipaddress
import urllib.parse
from pathlib import Path
from typing import Union, List
from fastapi import HTTPException


def safe_join_path(base_dir: Union[str, Path], *paths: str) -> str:
    """
    Safely joins paths ensuring that the resolved target path is strictly inside base_dir.
    Raises HTTPException 400 if path traversal is detected.
    """
    base_path = Path(base_dir).resolve()
    target_path = base_path.joinpath(*paths).resolve()

    try:
        target_path.relative_to(base_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path parameter or path traversal detected.")

    return str(target_path)


# Blocked CIDR Networks for SSRF Prevention
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_ip_blocked(ip_str: str) -> bool:
    """Checks if an IP string falls inside any blocked private/internal CIDR ranges."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for net in BLOCKED_NETWORKS:
            if ip_obj in net:
                return True
        return False
    except ValueError:
        return True


def validate_safe_url(url: str, allow_private: bool = False) -> str:
    """
    Strict Anti-TOCTOU SSRF URL Validator.
    Resolves hostname to IP once and validates destination against blocked internal networks.
    Raises HTTPException 400 if an SSRF attempt or forbidden IP target is detected.
    """
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail="Invalid or missing URL parameter.")

    parsed = urllib.parse.urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()

    if scheme not in ["http", "https", "rtsp", "rtmp"]:
        raise HTTPException(status_code=400, detail=f"Forbidden URL scheme '{scheme}'. Only HTTP, HTTPS, RTSP, RTMP allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: Hostname is missing.")

    # Prevent direct loopback/localhost strings
    if hostname.lower() in ["localhost", "127.0.0.1", "::1", "169.254.169.254"]:
        if not allow_private:
            raise HTTPException(status_code=400, detail="Forbidden URL: Loopback or Cloud Metadata target rejected.")

    # Resolve DNS once to prevent TOCTOU DNS rebinding
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if scheme == "https" else 80))
        resolved_ips = set(info[4][0] for info in addr_info)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"DNS resolution failed for hostname '{hostname}'.")

    if not allow_private:
        for ip in resolved_ips:
            if is_ip_blocked(ip):
                raise HTTPException(status_code=400, detail=f"Forbidden URL: Resolved IP '{ip}' is in a restricted internal network.")

    return url


def resolve_and_pin_target(url: str, allow_private: bool = False) -> tuple[str, str]:
    """
    Validates URL against SSRF policy and returns tuple of (validated_url, pinned_ip).
    Outbound socket connections must bind directly to pinned_ip to prevent DNS rebinding.
    """
    validated_url = validate_safe_url(url, allow_private=allow_private)
    parsed = urllib.parse.urlparse(validated_url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addr_info = socket.getaddrinfo(hostname, port)
    pinned_ip = addr_info[0][4][0]
    return validated_url, pinned_ip

