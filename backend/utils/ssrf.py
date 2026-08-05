import socket
import ipaddress
import urllib.parse
from fastapi import HTTPException

PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # Covers 169.254.169.254 AWS/GCP/Azure metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]

ALLOWED_SCHEMES = {"http", "https"}


def is_ip_private(ip_str: str) -> bool:
    try:
        # Strip IPv6 zone index if present
        clean_ip = ip_str.split("%")[0]
        ip = ipaddress.ip_address(clean_ip)

        # Unmap IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
        if hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_multicast or
            ip.is_reserved or
            ip.is_unspecified or
            any(ip in net for net in PRIVATE_NETWORKS)
        )
    except ValueError:
        return True


def validate_proxy_url(url: str, allow_private: bool = False) -> str:
    """
    SEC-05 FIX: Validates target URL against SSRF and DNS rebinding attacks:
    - Enforces http/https schemes.
    - Blocks localhost, 127.0.0.1, 169.254.169.254, internal domain names (.local, .internal, .lan).
    - Resolves hostname to all A/AAAA records and verifies NONE resolve to private/reserved networks.
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail=f"Scheme '{parsed.scheme}' not allowed. Must be http or https.")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid target hostname")

    # Block well-known internal hostname suffixes
    lower_host = hostname.lower()
    if any(lower_host.endswith(suffix) for suffix in (".local", ".internal", ".lan", ".home.arpa", ".invalid")):
        raise HTTPException(status_code=403, detail="Access to internal domain suffixes is prohibited.")

    if not allow_private:
        # Check direct IP string first
        try:
            direct_ip = ipaddress.ip_address(hostname)
            if is_ip_private(str(direct_ip)):
                raise HTTPException(status_code=403, detail="Access to private or restricted network addresses is prohibited.")
        except ValueError:
            pass  # Hostname is a domain name, proceed to DNS resolution

        # Resolve hostname and check all returned IPs (DNS rebinding defense step 1)
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            if not addr_info:
                raise HTTPException(status_code=400, detail=f"Could not resolve hostname '{hostname}'")

            for family, _, _, _, sockaddr in addr_info:
                ip_addr = sockaddr[0]
                if is_ip_private(ip_addr):
                    raise HTTPException(
                        status_code=403,
                        detail="Access to private or restricted network addresses is prohibited (resolved private IP)."
                    )
        except socket.gaierror:
            raise HTTPException(status_code=400, detail=f"Could not resolve hostname '{hostname}'")

    return url
