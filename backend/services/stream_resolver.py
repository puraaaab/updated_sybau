"""
Stream Resolver — Protocol Adapter for multi-source video ingestion.

Supports:
  • RTSP     (rtsp://…)          — pass-through, native OpenCV
  • HTTP/HLS (http(s)://…*.m3u8) — pass-through, native OpenCV
  • ONVIF    (onvif://…)         — reserved for future NVR/DVR integration
  • YouTube  (youtube.com/live…)  — resolved via yt-dlp to direct HLS manifest

Resolved URLs are cached with configurable TTL (default 2 hours).
"""

import subprocess
import time
import threading
import re

# Cache: camera_id -> {"url": resolved_url, "expiry": timestamp}
_resolved_cache = {}
_cache_lock = threading.Lock()

# Default cache TTL: 2 hours (YouTube HLS manifests expire in 4-6h)
CACHE_TTL_SECONDS = 7200

# Patterns for YouTube URLs
_YOUTUBE_PATTERNS = [
    re.compile(r"(https?://)?(www\.)?youtube\.com/(watch|live)"),
    re.compile(r"(https?://)?(www\.)?youtu\.be/"),
    re.compile(r"(https?://)?.*youtube\.com/.*[?&]v="),
]


def is_youtube_url(url: str) -> bool:
    """Check whether the given URL is a YouTube video/live stream."""
    return any(pat.search(url) for pat in _YOUTUBE_PATTERNS)


def _resolve_youtube(url: str) -> str | None:
    """
    Uses yt-dlp python library to extract the direct HLS/DASH manifest URL for a YouTube
    live stream.  Returns None on failure.
    """
    try:
        import yt_dlp
        ydl_opts = {'format': 'best', 'quiet': True, 'noplaylist': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'url' in info:
                # Some extractors return a list of formats, but 'url' usually has the best one if format=best
                return info['url']
    except ImportError:
        print("[StreamResolver] yt-dlp is not installed. Install with: pip install yt-dlp")
    except Exception as e:
        print(f"[StreamResolver] yt-dlp error: {e}")
    return None


def resolve_stream_url(camera_id: str, raw_url: str) -> str | None:
    """
    Resolves a camera's configured stream URL to a URL that OpenCV
    VideoCapture can open directly.

    For RTSP/HLS/HTTP streams, returns the URL as-is.
    For YouTube Live URLs, resolves via yt-dlp with caching.

    Returns None if resolution fails entirely.
    """
    if not raw_url:
        return None

    # ── ONVIF / NVR URI Resolver ──────────────────────────────────────────
    lower_url = raw_url.lower()
    if lower_url.startswith("onvif://"):
        # Format: onvif://username:password@ip:port/profile
        from .onvif_discovery import onvif_media_client
        try:
            # Parse credentials and target host
            parts = raw_url[8:].split("@", 1)
            creds = parts[0].split(":", 1) if "@" in raw_url else ["", ""]
            host_part = parts[1] if "@" in raw_url else parts[0]
            ip_port = host_part.split("/")[0].split(":")
            ip = ip_port[0]
            port = int(ip_port[1]) if len(ip_port) > 1 else 80
            return f"rtsp://{creds[0]}:{creds[1]}@{ip}:554/Streaming/Channels/101" if creds[0] else f"rtsp://{ip}:554/live/ch0"
        except Exception:
            return raw_url

    if lower_url.startswith("nvr://"):
        # Format: nvr://vendor:user:pass@ip:port/channel
        from .nvr_adapter import nvr_adapter
        try:
            # Parse nvr://hikvision:admin:pass@192.168.1.100:554/1
            parts = raw_url[6:].split("@", 1)
            meta = parts[0].split(":")
            vendor = meta[0]
            user = meta[1] if len(meta) > 1 else None
            pwd = meta[2] if len(meta) > 2 else None
            host_chan = parts[1].split("/")
            ip_port = host_chan[0].split(":")
            ip = ip_port[0]
            port = int(ip_port[1]) if len(ip_port) > 1 else 554
            channel = int(host_chan[1]) if len(host_chan) > 1 else 1
            return nvr_adapter.build_channel_url(vendor, ip, port, channel, user, pwd)
        except Exception:
            return raw_url

    # ── RTSP / direct HTTP(S) / HLS / local video files ──────────────────
    if not is_youtube_url(raw_url):
        return raw_url


    # ── YouTube Live adapter ─────────────────────────────────────────────
    now = time.time()

    with _cache_lock:
        cached = _resolved_cache.get(camera_id)
        if cached and now < cached["expiry"]:
            return cached["url"]

    print(f"[StreamResolver] Resolving YouTube Live -> direct stream for {camera_id}")
    resolved = _resolve_youtube(raw_url)

    if resolved:
        with _cache_lock:
            _resolved_cache[camera_id] = {
                "url": resolved,
                "expiry": now + CACHE_TTL_SECONDS,
            }
        print(f"[StreamResolver] Resolved {camera_id} successfully (cached for {CACHE_TTL_SECONDS}s)")
        return resolved

    # Fallback: try the raw URL directly (some YouTube URLs work with
    # pafy/OpenCV on specific builds)
    print(f"[StreamResolver] Could not resolve {camera_id}, returning raw URL as fallback")
    return raw_url


def invalidate_cache(camera_id: str):
    """Force re-resolution on next call for this camera."""
    with _cache_lock:
        _resolved_cache.pop(camera_id, None)


def invalidate_all():
    """Clear the entire resolution cache."""
    with _cache_lock:
        _resolved_cache.clear()
