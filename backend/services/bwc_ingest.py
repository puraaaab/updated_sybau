"""
Body-Worn Camera (BWC) Docking Station & Offload Protocol Adapter.

Handles:
  • Batch video file uploads from bodycam docking stations
  • Metadata extraction (Officer ID, Badge Number, Device Serial, GPS Telemetry)
  • Storing offloaded clips into recordings directory with DB registration
"""

import os
import shutil
import datetime
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..database.models import Camera

logger = logging.getLogger(__name__)

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))


class BWCFileIngestService:
    """Processes bodycam video file offloading from docking stations."""

    @staticmethod
    def process_bwc_upload(
        db: Session,
        officer_id: str,
        badge_number: str,
        device_serial: str,
        file_path: str,
        original_filename: str
    ) -> Dict[str, Any]:
        """
        Registers an offloaded bodycam video clip, saves it under storage/recordings/bwc_{serial}/,
        and ensures a BWC Camera record exists in the database.
        """
        camera_id = f"bwc_{device_serial.lower()}"
        bwc_dir = os.path.join(STORAGE_DIR, camera_id)
        os.makedirs(bwc_dir, exist_ok=True)

        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target_filename = f"bwc_{now_str}_{original_filename}"
        target_path = os.path.join(bwc_dir, target_filename)

        # Move/copy file to recordings directory
        shutil.copy2(file_path, target_path)
        file_size = os.path.getsize(target_path)

        # Ensure Camera record exists for this bodycam
        cam = db.query(Camera).filter(Camera.id == camera_id).first()
        if not cam:
            cam = Camera(
                id=camera_id,
                name=f"BWC Badge #{badge_number} ({officer_id})",
                stream_url=target_path,
                status="online",
                width=1920,
                height=1080
            )
            db.add(cam)
            db.commit()

        logger.info(f"[BWC Ingest] Offloaded {target_filename} ({file_size} bytes) for Officer {officer_id} (Badge #{badge_number})")
        return {
            "status": "success",
            "camera_id": camera_id,
            "filename": target_filename,
            "file_size": file_size,
            "officer_id": officer_id,
            "badge_number": badge_number,
            "device_serial": device_serial,
            "saved_path": target_path
        }

bwc_ingest_service = BWCFileIngestService()
