"""
NVR / DVR Multi-Channel Protocol Adapter.

Provides stream path resolution for multi-channel NVR systems:
  • Hikvision NVR: rtsp://user:pass@host:554/Streaming/Channels/{channel}01 (Main) or {channel}02 (Sub)
  • Dahua NVR:     rtsp://user:pass@host:554/cam/realmonitor?channel={channel}&subtype=0
  • CP PLUS:       rtsp://user:pass@host:554/cam/realmonitor?channel={channel}&subtype=0
  • Axis NVR:      rtsp://user:pass@host:554/axis-media/media.amp?camera={channel}
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class NVRAdapter:
    """Resolves camera channel paths for enterprise NVR/DVR systems."""

    VENDOR_PATTERNS = {
        "hikvision": "rtsp://{credentials}{ip}:{port}/Streaming/Channels/{channel}01",
        "dahua": "rtsp://{credentials}{ip}:{port}/cam/realmonitor?channel={channel}&subtype=0",
        "cpplus": "rtsp://{credentials}{ip}:{port}/cam/realmonitor?channel={channel}&subtype=0",
        "axis": "rtsp://{credentials}{ip}:{port}/axis-media/media.amp?camera={channel}",
        "generic": "rtsp://{credentials}{ip}:{port}/ch{channel}/main"
    }

    @classmethod
    def build_channel_url(
        cls,
        vendor: str,
        ip: str,
        port: int = 554,
        channel: int = 1,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> str:
        pattern = cls.VENDOR_PATTERNS.get(vendor.lower(), cls.VENDOR_PATTERNS["generic"])
        creds = f"{username}:{password}@" if username and password else ""
        return pattern.format(credentials=creds, ip=ip, port=port, channel=channel)

nvr_adapter = NVRAdapter()
