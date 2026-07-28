import socket
import ipaddress
import urllib.parse
from fastapi import HTTPException

PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]

ALLOWED_SCHEMES = {"http", "https"}

def is_ip_private(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return True

def validate_proxy_url(url: str, allow_private: bool = False) -> str:
    """
    Validates target URL against SSRF attacks:
    - Enforces http/https schemes.
    - Resolves hostname and verifies that IP is not in private/reserved ranges.
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
        
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail=f"Scheme '{parsed.scheme}' not allowed. Must be http or https.")
        
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid target hostname")

    if not allow_private:
        # Resolve hostname to IP addresses
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in addr_info:
                ip = sockaddr[0]
                if is_ip_private(ip):
                    raise HTTPException(status_code=403, detail="Access to private or restricted network addresses is prohibited.")
        except socket.gaierror:
            raise HTTPException(status_code=400, detail=f"Could not resolve hostname '{hostname}'")
            
    return url
