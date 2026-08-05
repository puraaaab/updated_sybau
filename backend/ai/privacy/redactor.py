"""
Privacy Redaction Engine — Face and License Plate Masking Module.

Supports:
  • Global System Setting toggle (configs/privacy.json)
  • Independent Face Redaction toggle (redact_faces)
  • Independent License Plate Redaction toggle (redact_plates)
  • Per-request override for evidence export & snapshot API endpoints
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Optional
from ...config.service import get_privacy_settings

logger = logging.getLogger(__name__)

class PrivacyRedactor:
    """
    Applies Gaussian blurring to face and license plate bounding box regions.
    """

    @staticmethod
    def blur_region(frame: np.ndarray, bbox: List[int], kernel_size: int = 51) -> np.ndarray:
        """
        Applies strong Gaussian blur to bounding box area [x1, y1, x2, y2].
        """
        h_frame, w_frame = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
        
        # Clamp coordinates to frame boundaries
        x1 = max(0, min(x1, w_frame - 1))
        y1 = max(0, min(y1, h_frame - 1))
        x2 = max(0, min(x2, w_frame))
        y2 = max(0, min(y2, h_frame))

        if x2 <= x1 or y2 <= y1:
            return frame

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return frame

        # Ensure kernel size is odd
        k = kernel_size if kernel_size % 2 != 0 else kernel_size + 1
        k = max(7, min(k, min(roi.shape[0], roi.shape[1]) | 1))

        blurred_roi = cv2.GaussianBlur(roi, (k, k), 0)
        frame[y1:y2, x1:x2] = blurred_roi
        return frame

    @classmethod
    def redact_frame(
        cls,
        frame: np.ndarray,
        detections: List[Dict],
        mask_faces: Optional[bool] = None,
        mask_plates: Optional[bool] = None
    ) -> np.ndarray:
        """
        Applies privacy redaction to a copy of the frame.
        
        If mask_faces / mask_plates are None, defaults to system settings in configs/privacy.json.
        """
        if frame is None or frame.size == 0:
            return frame

        cfg = get_privacy_settings()
        master_enabled = cfg.get("enabled", False)

        # Determine effective toggles
        should_mask_faces = mask_faces if mask_faces is not None else (master_enabled and cfg.get("redact_faces", True))
        should_mask_plates = mask_plates if mask_plates is not None else (master_enabled and cfg.get("redact_plates", True))

        if not should_mask_faces and not should_mask_plates:
            return frame

        out_frame = frame.copy()
        k_size = cfg.get("blur_kernel_size", 51)

        face_classes = {"face", "person"}
        plate_classes = {"license_plate", "plate", "car", "truck", "bus", "vehicle"}

        for det in detections:
            bbox = det.get("bbox") or det.get("box")
            if not bbox or len(bbox) < 4:
                continue

            c_name = str(det.get("class_name", "")).lower()

            # Face redaction
            if should_mask_faces and (c_name == "face" or det.get("type") == "face"):
                cls.blur_region(out_frame, bbox, k_size)
            elif should_mask_faces and c_name == "person":
                # Mask head/face region of person bounding box (top 25% of height)
                x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
                head_h = max(10, int((y2 - y1) * 0.25))
                cls.blur_region(out_frame, [x1, y1, x2, y1 + head_h], k_size)

            # License plate redaction
            if should_mask_plates and (c_name in {"license_plate", "plate"} or det.get("type") == "plate"):
                cls.blur_region(out_frame, bbox, k_size)
            elif should_mask_plates and c_name in {"car", "truck", "bus", "vehicle"} and "plate_bbox" in det:
                plate_box = det["plate_bbox"]
                if plate_box and len(plate_box) >= 4:
                    cls.blur_region(out_frame, plate_box, k_size)

        return out_frame

privacy_redactor = PrivacyRedactor()
