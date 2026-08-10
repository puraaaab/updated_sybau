"""
Body-Worn Camera (BWC) Live Streaming Protocol Adapter.

Handles:
  • Live RTMP/RTSP stream registration for cellular/Wi-Fi bodycams
  • Dynamic MediaMTX path mapping and RTMP stream URL generation
  • Automatic DB registration of active live BWC units with telemetry metadata
"""

import os
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..database.models import Camera

logger = logging.getLogger(__name__)

MEDIAMTX_RTSP_HOST = os.getenv("MEDIAMTX_HOST", "localhost")
MEDIAMTX_RTSP_PORT = int(os.getenv("MEDIAMTX_RTSP_PORT", "8554"))
MEDIAMTX_RTMP_PORT = int(os.getenv("MEDIAMTX_RTMP_PORT", "1935"))


class BWCLiveIngestService:
    """Manages active live RTMP/RTSP stream ingestion from mobile Body-Worn Cameras."""

    @staticmethod
    def register_live_bwc(
        db: Session,
        officer_id: str,
        badge_number: str,
        device_serial: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        stream_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registers an active cellular live BWC stream, builds the RTMP ingest URL
        and RTSP consumer URL, and inserts/updates the Camera record in the database.
        """
        camera_id = f"bwc_live_{device_serial.lower()}"
        path_name = stream_path or f"bwc/{device_serial.lower()}"

        ingest_rtmp_url = f"rtmp://{MEDIAMTX_RTSP_HOST}:{MEDIAMTX_RTMP_PORT}/{path_name}"
        consumer_rtsp_url = f"rtsp://{MEDIAMTX_RTSP_HOST}:{MEDIAMTX_RTSP_PORT}/{path_name}"

        cam = db.query(Camera).filter(Camera.id == camera_id).first()
        cam_name = f"Live BWC Badge #{badge_number} ({officer_id})"

        if not cam:
            cam = Camera(
                id=camera_id,
                name=cam_name,
                stream_url=consumer_rtsp_url,
                status="online",
                latitude=lat if lat is not None else 21.1700,
                longitude=lng if lng is not None else 72.8000,
                location=f"Field Unit - Badge #{badge_number}",
                width=1920,
                height=1080
            )
            db.add(cam)
        else:
            cam.stream_url = consumer_rtsp_url
            cam.status = "online"
            if lat is not None:
                cam.latitude = lat
            if lng is not None:
                cam.longitude = lng
            cam.location = f"Field Unit - Badge #{badge_number}"

        db.commit()
        db.refresh(cam)

        logger.info(f"[BWC Live Ingest] Registered live stream for Officer {officer_id} (Badge #{badge_number}) -> {consumer_rtsp_url}")
        return {
            "status": "success",
            "camera_id": camera_id,
            "officer_id": officer_id,
            "badge_number": badge_number,
            "device_serial": device_serial,
            "rtmp_push_url": ingest_rtmp_url,
            "rtsp_consumer_url": consumer_rtsp_url,
            "latitude": cam.latitude,
            "longitude": cam.longitude
        }


bwc_live_ingest_service = BWCLiveIngestService()
