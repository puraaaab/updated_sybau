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

    # ── RTSP / direct HTTP(S) / HLS ──────────────────────────────────────
    if raw_url.lower().startswith("rtsp://"):
        return raw_url

    if raw_url.lower().endswith(".m3u8"):
        return raw_url

    # Non-YouTube http(s) URLs — assume direct stream
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
