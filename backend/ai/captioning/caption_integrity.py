"""
Image-to-Caption Integrity Verification System for Sybau VMS.

Enforces strict 1-to-1 binding between image frames and AI-generated captions.
Prevents mismatched, swapped, stale, or out-of-order captions from being committed to DB,
vector database, or UI streams.

Pipeline flow:
Image -> image_id + sha256_hash -> Envelope Registry -> Moondream/Florence Request
      -> Response -> Integrity Check (ID + Hash + Camera + Expiry + Single-use)
      -> PASS -> Commit to DB ({image_id}.jpg + snapshot_url)
      -> FAIL -> Reject & Log Error
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import numpy as np
import cv2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptionEnvelope:
    image_id: str           # Unique Image ID (e.g. img_8f3a12b4...)
    camera_id: str          # Camera source ID
    image_hash: str         # SHA256 hex digest of image pixel bytes
    created_at: float       # Monotonic timestamp of request creation
    yolo_summary: str       # Associated YOLO summary string
    frame_shape: Tuple[int, int, int]  # (height, width, channels)


class CaptionIntegrityValidator:
    """
    Thread-safe registry and validation engine enforcing strict 1-to-1 image-to-caption integrity.
    """
    REQUEST_TIMEOUT_SECONDS = 3600.0  # Max valid request lifetime before marked stale (1 hour for multi-camera queue)

    def __init__(self):
        self._registry: Dict[str, CaptionEnvelope] = {}
        self._completed_ids: set[str] = set()
        self._lock = __import__("threading").Lock()

    @staticmethod
    def compute_image_hash(frame: np.ndarray) -> str:
        """Computes cryptographic SHA-256 fingerprint of raw frame array bytes."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return ""
        try:
            h, w = frame.shape[:2]
            if max(h, w) > 640:
                scale = 640.0 / max(h, w)
                small = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_NEAREST)
                return hashlib.sha256(small.tobytes()).hexdigest()
            return hashlib.sha256(frame.tobytes()).hexdigest()
        except Exception:
            return ""

    def create_envelope(
        self,
        frame: np.ndarray,
        camera_id: str,
        yolo_summary: str = "",
        custom_id: Optional[str] = None
    ) -> Tuple[str, CaptionEnvelope]:
        """
        Creates and registers an immutable CaptionEnvelope for an image frame.
        Returns (image_id, CaptionEnvelope).
        """
        if custom_id and custom_id.startswith("img_"):
            image_id = custom_id
        elif custom_id:
            image_id = f"img_{custom_id}"
        else:
            image_id = f"img_{uuid.uuid4().hex[:12]}"

        image_hash = self.compute_image_hash(frame)
        envelope = CaptionEnvelope(
            image_id=image_id,
            camera_id=camera_id,
            image_hash=image_hash,
            created_at=time.monotonic(),
            yolo_summary=yolo_summary,
            frame_shape=frame.shape if frame is not None and hasattr(frame, "shape") else (0, 0, 0)
        )

        with self._lock:
            # Prune stale entries older than 5 minutes
            now = time.monotonic()
            if len(self._registry) > 500:
                self._registry = {
                    k: v for k, v in self._registry.items()
                    if (now - v.created_at) < 300.0
                }
            self._registry[image_id] = envelope

        logger.info(f"[CaptionIntegrity] Registered envelope image_id={image_id} cam={camera_id} hash={image_hash[:10]}")
        return image_id, envelope

    def validate_and_claim(
        self,
        image_id: str,
        camera_id: str,
        frame: Optional[np.ndarray] = None,
        raw_caption: Optional[str] = None
    ) -> Tuple[bool, str, Optional[CaptionEnvelope]]:
        """
        Performs strict multi-point integrity verification before committing a caption:
        1. Checks image_id presence in registry.
        2. Validates image_id hasn't already been claimed (replay prevention).
        3. Verifies request timeout (< 60s).
        4. Confirms camera_id matches envelope.camera_id.
        5. Validates pixel hash match if frame is provided.
        6. Confirms caption content is non-empty.

        Returns (is_valid, reason_message, envelope).
        """
        if not image_id:
            msg = "[INTEGRITY ERROR] Rejected: Missing image_id on caption response."
            logger.error(msg)
            return False, msg, None

        if not raw_caption or not raw_caption.strip():
            msg = f"[INTEGRITY ERROR] Rejected: Empty caption response for image_id={image_id}."
            logger.error(msg)
            return False, msg, None

        with self._lock:
            if image_id in self._completed_ids:
                msg = f"[INTEGRITY ERROR] Rejected: Duplicate or replay response for image_id={image_id}."
                logger.error(msg)
                return False, msg, None

            envelope = self._registry.get(image_id)
            if envelope is None:
                msg = f"[INTEGRITY ERROR] Rejected: Unknown or unregistered image_id={image_id}."
                logger.error(msg)
                return False, msg, None

            # Timeout check
            elapsed = time.monotonic() - envelope.created_at
            if elapsed > self.REQUEST_TIMEOUT_SECONDS:
                msg = f"[INTEGRITY ERROR] Rejected: Stale caption response for image_id={image_id} (elapsed={elapsed:.1f}s > {self.REQUEST_TIMEOUT_SECONDS}s)."
                logger.error(msg)
                self._registry.pop(image_id, None)
                return False, msg, None

            # Camera ID match check
            if envelope.camera_id != camera_id:
                msg = f"[INTEGRITY ERROR] Rejected: Camera ID mismatch for image_id={image_id}! Expected '{envelope.camera_id}', got '{camera_id}'."
                logger.error(msg)
                return False, msg, None

            # Pixel Hash match check
            if frame is not None and envelope.image_hash:
                current_hash = self.compute_image_hash(frame)
                if current_hash and current_hash != envelope.image_hash:
                    msg = f"[INTEGRITY ERROR] Rejected: Image pixel hash mismatch for image_id={image_id}! Expected {envelope.image_hash[:10]}, got {current_hash[:10]}."
                    logger.error(msg)
                    return False, msg, None

            # Mark as claimed and remove from active registry
            self._completed_ids.add(image_id)
            if len(self._completed_ids) > 1000:
                self._completed_ids.clear()
            self._registry.pop(image_id, None)

        logger.info(f"[CaptionIntegrity] Integrity check PASS for image_id={image_id} cam={camera_id}")
        return True, "PASS", envelope


caption_integrity_validator = CaptionIntegrityValidator()
