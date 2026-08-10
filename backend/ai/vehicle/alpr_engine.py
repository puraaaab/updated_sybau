"""
Two-Stage Automated License Plate Recognition (ALPR) Engine.

Stage 1: Bounding Box Detection & Homography Perspective Transformation (Deskewing)
Stage 2: OCR Extraction + Positional Character Correction (plate_parser.py)
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any, Optional, List
from .plate_parser import parse_plate

logger = logging.getLogger(__name__)


class ALPREngine:
    """Specialized License Plate Deskewing and Optical Character Recognition Engine."""

    @staticmethod
    def deskew_plate_crop(plate_crop: np.ndarray) -> np.ndarray:
        """
        Applies homography perspective transformation to correct rotated/slanted license plates.
        """
        if plate_crop is None or plate_crop.size == 0:
            return plate_crop

        h, w = plate_crop.shape[:2]
        if h < 10 or w < 30:
            return plate_crop

        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return plate_crop

        largest_contour = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(largest_contour)
        box = cv2.boxPoints(rect)
        box = np.int32(box)

        # Sort points: top-left, top-right, bottom-right, bottom-left
        pts = box.astype("float32")
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)

        rect_pts = np.zeros((4, 2), dtype="float32")
        rect_pts[0] = pts[np.argmin(s)]       # Top-left
        rect_pts[2] = pts[np.argmax(s)]       # Bottom-right
        rect_pts[1] = pts[np.argmin(diff)]    # Top-right
        rect_pts[3] = pts[np.argmax(diff)]    # Bottom-left

        width_a = np.sqrt(((rect_pts[2][0] - rect_pts[3][0]) ** 2) + ((rect_pts[2][1] - rect_pts[3][1]) ** 2))
        width_b = np.sqrt(((rect_pts[1][0] - rect_pts[0][0]) ** 2) + ((rect_pts[1][1] - rect_pts[0][1]) ** 2))
        max_w = max(int(width_a), int(width_b), w)

        height_a = np.sqrt(((rect_pts[1][0] - rect_pts[2][0]) ** 2) + ((rect_pts[1][1] - rect_pts[2][1]) ** 2))
        height_b = np.sqrt(((rect_pts[0][0] - rect_pts[3][0]) ** 2) + ((rect_pts[0][1] - rect_pts[3][1]) ** 2))
        max_h = max(int(height_a), int(height_b), h)

        dst_pts = np.array([
            [0, 0],
            [max_w - 1, 0],
            [max_w - 1, max_h - 1],
            [0, max_h - 1]
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(rect_pts, dst_pts)
        warped = cv2.warpPerspective(plate_crop, M, (max_w, max_h))
        return warped if warped.size > 0 else plate_crop

    def process_plate(self, plate_crop: np.ndarray, ocr_engine: Any = None) -> Dict[str, Any]:
        """
        Executes two-stage ALPR: deskews crop, runs OCR, and parses raw text through Indian plate rules.
        """
        if plate_crop is None or plate_crop.size == 0:
            return {"raw_text": "", "parsed_plate": None, "confidence": 0.0}

        deskewed = self.deskew_plate_crop(plate_crop)

        raw_text = ""
        confidence = 0.0

        if ocr_engine is not None:
            try:
                results = ocr_engine.readtext(deskewed)
                if results:
                    raw_text = "".join([res[1] for res in results]).strip()
                    confidence = float(np.mean([res[2] for res in results]))
            except Exception as e:
                logger.debug(f"[ALPR] OCR execution note: {e}")

        parsed_res = parse_plate(raw_text)
        return {
            "raw_text": raw_text,
            "parsed_plate": parsed_res.get("parsed"),
            "confidence": confidence,
            "reason": parsed_res.get("reason"),
            "confidence_type": parsed_res.get("confidence")
        }


alpr_engine = ALPREngine()
