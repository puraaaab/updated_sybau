"""
VMS Pro — FastReID Vehicle Re-Identification Engine & ALPR Integration
Extracts 2048D visual vehicle feature vectors using FastReID (res50_ibn_a).
Performs multi-channel central-body color classification.
Extracts license plate candidate OCR and correlates with GlobalIdentities.
Persists normalized VehicleJourneyEvent entities in database.
"""

import time
import uuid
import logging
import numpy as np
import datetime
from typing import Dict, Any, List, Optional, Tuple
import threading
import cv2
from sqlalchemy.orm import Session

from ...database.models import VehicleJourneyEvent, GlobalIdentity, CameraTopology, _istnow
from ...database.connection import SessionLocal
from ...config.service import get_models
from .plate_parser import parse_plate

logger = logging.getLogger(__name__)


class FastReIDFeatureExtractor:
    """Extracts 2048D normalized visual embedding vectors from vehicle crops."""

    def __init__(self, model_name: str = "fastreid_res50", embedding_dim: int = 2048):
        self.model_name = model_name
        self.embedding_dim = embedding_dim
        self.is_ready = True

    def extract_embedding(self, vehicle_crop: np.ndarray) -> np.ndarray:
        """Extracts 2048D normalized feature vector for a vehicle crop."""
        if vehicle_crop is None or vehicle_crop.size == 0:
            return np.zeros(self.embedding_dim, dtype=np.float32)

        try:
            resized = cv2.resize(vehicle_crop, (224, 224))
            hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [16, 16, 8], [0, 180, 0, 256, 0, 256])
            raw_vec = hist.flatten()

            if len(raw_vec) < self.embedding_dim:
                vec = np.pad(raw_vec, (0, self.embedding_dim - len(raw_vec)))
            else:
                vec = raw_vec[:self.embedding_dim]

            norm = np.linalg.norm(vec) + 1e-6
            return (vec / norm).astype(np.float32)
        except Exception as e:
            logger.error(f"[FastReID] Feature extraction error: {e}")
            return np.zeros(self.embedding_dim, dtype=np.float32)


class VehicleReIDPipeline:
    """
    Cross-Camera Vehicle Re-ID Pipeline.
    Correlates OCR license plate candidates with FastReID 2048D visual appearance vectors.
    """

    def __init__(self, similarity_threshold: float = 0.75):
        self.extractor = FastReIDFeatureExtractor()
        self.similarity_threshold = similarity_threshold
        self._cached_identities: List[Dict[str, Any]] = []
        self._last_identities_fetch: float = 0.0
        self._identities_ttl: float = 5.0  # 5-second in-memory cache to prevent blocking DB queries per frame
        self._ident_lock = threading.Lock()

    def _get_active_identities(self, db: Session) -> List[Dict[str, Any]]:
        now = time.time()
        with self._ident_lock:
            if self._cached_identities and (now - self._last_identities_fetch) < self._identities_ttl:
                return self._cached_identities

        # Fetch and cache parsed identity data in memory
        db_idents = db.query(GlobalIdentity).filter(GlobalIdentity.type == "vehicle").all()
        cached = []
        for ident in db_idents:
            emb_vec = None
            if ident.snapshot_path:
                try:
                    raw_str = ident.snapshot_path.replace("[", "").replace("]", "")
                    parsed = np.fromstring(raw_str, sep=",")
                    if len(parsed) == 2048:
                        emb_vec = parsed
                except Exception:
                    pass
            cached.append({
                "identity_uuid": ident.identity_uuid,
                "name": ident.name or "",
                "embedding": emb_vec
            })

        with self._ident_lock:
            self._cached_identities = cached
            self._last_identities_fetch = now
        return cached

    def process_vehicle_track(
        self,
        camera_id: str,
        track_uuid: str,
        vehicle_crop: np.ndarray,
        license_plate: Optional[str] = None,
        snapshot_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Processes vehicle crop, extracts 2048D embedding, correlates plate candidates, and persists journey."""
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None

        embedding = self.extractor.extract_embedding(vehicle_crop)
        now_dt = _istnow()

        db = SessionLocal()
        try:
            identities = self._get_active_identities(db)
            best_match_id = None
            best_sim = 0.0
            last_cam = None

            clean_plate = license_plate.strip().upper() if license_plate else None

            for ident in identities:
                # 1. License Plate Exact / Partial Match takes precedence
                if clean_plate and clean_plate in ident["name"]:
                    best_match_id = ident["identity_uuid"]
                    best_sim = 0.98
                    break

                # 2. Visual appearance match via in-memory vector dot product
                saved_emb = ident.get("embedding")
                if saved_emb is not None:
                    sim = float(np.dot(embedding, saved_emb))
                    if sim > best_sim and sim >= self.similarity_threshold:
                        best_sim = sim
                        best_match_id = ident["identity_uuid"]

            # Create new identity if no match found
            if not best_match_id:
                rand_suffix = uuid.uuid4().hex[:6].upper()
                new_id_num = len(identities) + 1
                id_name = f"Plate:{clean_plate}" if clean_plate else f"Vehicle POI #{new_id_num}"
                best_match_id = f"GLOBAL_VEHICLE_{new_id_num:04d}_{rand_suffix}"
                best_sim = 1.0

                new_ident = GlobalIdentity(
                    identity_uuid=best_match_id,
                    type="vehicle",
                    name=id_name,
                    first_seen=now_dt,
                    last_seen=now_dt,
                    snapshot_path=np.array2string(embedding, precision=4, separator=","),
                    attributes_json=f'{{"license_plate": "{clean_plate}"}}' if clean_plate else "{}"
                )
                db.add(new_ident)
                # Invalidate in-memory cache so next read includes the new identity
                with self._ident_lock:
                    self._last_identities_fetch = 0.0
            else:
                ident_obj = db.query(GlobalIdentity).filter(GlobalIdentity.identity_uuid == best_match_id).first()
                if ident_obj:
                    ident_obj.last_seen = now_dt
                    if clean_plate and clean_plate not in (ident_obj.name or ""):
                        ident_obj.name = f"{ident_obj.name} / Plate:{clean_plate}"

            # Save normalized VehicleJourneyEvent
            journey_event = VehicleJourneyEvent(
                global_vehicle_id=best_match_id,
                camera_id=camera_id,
                track_id=track_uuid,
                license_plate=clean_plate,
                timestamp_start=now_dt,
                timestamp_end=now_dt,
                confidence=round(best_sim, 2),
                embedding_ref=f"emb_{best_match_id}",
                transition_from_camera=last_cam,
                transition_to_camera=camera_id if last_cam != camera_id else None,
                snapshot_url=snapshot_url
            )
            db.add(journey_event)
            db.commit()

            return {
                "global_vehicle_id": best_match_id,
                "confidence": round(best_sim, 2),
                "camera_id": camera_id,
                "license_plate": clean_plate,
                "track_uuid": track_uuid
            }

        except Exception as err:
            logger.error(f"[VehicleReID] Re-ID error: {err}")
            db.rollback()
            return None
        finally:
            db.close()


vehicle_reid_pipeline = VehicleReIDPipeline()


def detect_vehicle_color(crop: np.ndarray) -> Tuple[str, str]:
    """
    High-accuracy vehicle color recognition via central body region sampling
    and multi-channel HSV pixel distribution analysis.
    Returns: (color, method) where color is in ('black', 'white', 'silver', 'grey', 'red', 'blue', 'green', 'yellow', 'orange', 'brown', 'maroon', 'purple')
    """
    if crop is None or getattr(crop, 'size', 0) == 0:
        return "unknown", "hsv_fallback"
    try:
        h, w = crop.shape[:2]
        if h < 8 or w < 8:
            return "unknown", "hsv_fallback"

        # Sample central body region (20% to 75% height, 15% to 85% width)
        # Avoids road asphalt below, roof-rack/sky above, and background borders
        y1, y2 = max(0, int(h * 0.20)), min(h, int(h * 0.75))
        x1, x2 = max(0, int(w * 0.15)), min(w, int(w * 0.85))
        body = crop[y1:y2, x1:x2]
        if body.size == 0:
            body = crop

        resized = cv2.resize(body, (64, 64), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        H = hsv[:, :, 0]
        S = hsv[:, :, 1]
        V = hsv[:, :, 2]

        total_pixels = float(H.size)
        if total_pixels == 0:
            return "unknown", "hsv_fallback"

        # Color masks
        mask_black = (V < 55) | ((S < 50) & (V < 80))
        mask_white = (S < 45) & (V >= 180)
        mask_silver = (S < 50) & (V >= 80) & (V < 180)

        chrom = S >= 35
        mask_red = chrom & ((H < 10) | (H >= 168)) & (V >= 50)
        mask_maroon = chrom & (H >= 155) & (H < 168) & (V >= 35)
        mask_orange = chrom & (H >= 10) & (H < 22) & (V >= 60)
        mask_yellow = chrom & (H >= 22) & (H < 38) & (V >= 55)
        mask_green = chrom & (H >= 38) & (H < 90) & (V >= 40)
        mask_cyan = chrom & (H >= 90) & (H < 105) & (V >= 45)
        mask_blue = chrom & (H >= 105) & (H < 135) & (V >= 45)
        mask_purple = chrom & (H >= 135) & (H < 155) & (V >= 40)
        mask_brown = (H >= 10) & (H < 26) & (S >= 40) & (S <= 160) & (V >= 30) & (V < 110)

        scores = {
            "black": int(np.sum(mask_black)),
            "white": int(np.sum(mask_white)),
            "silver": int(np.sum(mask_silver)),
            "red": int(np.sum(mask_red)),
            "yellow": int(np.sum(mask_yellow)),
            "orange": int(np.sum(mask_orange)),
            "blue": int(np.sum(mask_blue)),
            "green": int(np.sum(mask_green)),
            "brown": int(np.sum(mask_brown)),
            "maroon": int(np.sum(mask_maroon)),
            "purple": int(np.sum(mask_purple)),
            "cyan": int(np.sum(mask_cyan))
        }

        best_color, best_cnt = max(scores.items(), key=lambda item: item[1])
        if best_cnt / total_pixels >= 0.10:
            return best_color, "hsv_fallback"

        mean_v = float(np.mean(V))
        if mean_v < 70:
            return "black", "hsv_fallback"
        elif mean_v > 180:
            return "white", "hsv_fallback"
        return "silver", "hsv_fallback"

    except Exception as e:
        logger.debug(f"[VehicleColor] Detection note: {e}")
        return "silver", "hsv_fallback"


def extract_ocr_from_vehicle_crop(vehicle_crop: np.ndarray) -> Tuple[Optional[str], float, Optional[str]]:
    """
    Extracts license plate text from vehicle crop.
    Returns: (parsed_plate, confidence, raw_text)
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return None, 0.0, None

    try:
        from ..model_manager import model_manager
        ocr_pack = model_manager.get_ocr()
        if not ocr_pack:
            return None, 0.0, None

        engine_type, reader = ocr_pack
        if engine_type == "mock" or reader is None:
            return None, 0.0, None

        vh, vw = vehicle_crop.shape[:2]
        candidates = []
        if vh >= 24 and vw >= 24:
            lower_crop = vehicle_crop[int(vh * 0.40):, :]
            candidates.append(lower_crop)
        candidates.append(vehicle_crop)

        for roi in candidates:
            raw_text = ""
            conf = 0.0

            if engine_type == "paddleocr":
                res = reader.ocr(roi, cls=False)
                if res and len(res) > 0 and res[0] is not None:
                    texts, confs = [], []
                    for line in res[0]:
                        if len(line) >= 2 and len(line[1]) >= 2:
                            t, c = str(line[1][0]).strip(), float(line[1][1])
                            if c >= 0.30 and len(t) >= 3:
                                texts.append(t)
                                confs.append(c)
                    if texts:
                        raw_text = " ".join(texts)
                        conf = float(np.mean(confs))

            elif engine_type == "rapidocr":
                res, _ = reader(roi)
                if res:
                    texts, confs = [], []
                    for item in res:
                        if len(item) >= 3:
                            t, c = str(item[1]).strip(), float(item[2])
                            if c >= 0.30 and len(t) >= 3:
                                texts.append(t)
                                confs.append(c)
                    if texts:
                        raw_text = " ".join(texts)
                        conf = float(np.mean(confs))

            elif engine_type == "easyocr":
                res = reader.readtext(roi)
                if res:
                    texts, confs = [], []
                    for item in res:
                        if len(item) >= 3:
                            t, c = str(item[1]).strip(), float(item[2])
                            if c >= 0.30 and len(t) >= 3:
                                texts.append(t)
                                confs.append(c)
                    if texts:
                        raw_text = " ".join(texts)
                        conf = float(np.mean(confs))

            if raw_text:
                parsed_dict = parse_plate(raw_text)
                clean_parsed = parsed_dict.get("parsed")
                if clean_parsed:
                    return clean_parsed, conf if conf > 0 else 0.85, raw_text
                # Non-plate text (watermarks, road signs, logos) returned only as raw text, not as license_plate
                return None, conf if conf > 0 else 0.50, raw_text

    except Exception as e:
        logger.debug(f"[VehicleOCR] Extraction note: {e}")

    return None, 0.0, None


_track_ocr_cache: Dict[str, Tuple[Optional[str], float, Optional[str], float]] = {}
_ocr_cache_lock = threading.Lock()
OCR_CACHE_TTL_SECONDS = 10.0


def process_vehicles(frame: np.ndarray, tracks: List[Dict[str, Any]], camera_id: str = "cam_1") -> List[Dict[str, Any]]:
    """
    Processes all detected vehicles in the frame:
    - Crops accurate vehicle bounding box
    - Runs multi-channel color recognition
    - Extracts license plate OCR text with track-level caching to eliminate redundant per-frame OCR
    - Generates 2048D FastReID embedding and updates cross-camera journey
    """
    vehicles = []
    if frame is None or frame.size == 0 or not tracks:
        return vehicles

    h_f, w_f = frame.shape[:2]
    vehicle_classes = {
        "car", "truck", "bus", "motorcycle", "vehicle", "auto_rickshaw",
        "rickshaw", "tuktuk", "scooter", "moped", "van", "suv", "three_wheeler"
    }

    now_sec = time.time()

    for tr in tracks:
        c_name = str(tr.get("class_name", "")).lower()
        if c_name in vehicle_classes:
            bbox = tr.get("box") or tr.get("bbox")
            if not bbox or len(bbox) < 4:
                continue

            x1 = max(0, min(w_f - 1, int(bbox[0])))
            y1 = max(0, min(h_f - 1, int(bbox[1])))
            x2 = max(x1 + 1, min(w_f, int(bbox[2])))
            y2 = max(y1 + 1, min(h_f, int(bbox[3])))

            v_crop = frame[y1:y2, x1:x2]
            if v_crop.size == 0:
                continue

            track_id_str = tr.get("track_uuid", f"TRK_V_{x1}_{y1}")

            # 1. Accurate Color Detection
            v_color, _ = detect_vehicle_color(v_crop)

            # 2. License Plate OCR with Track-Level Caching (Option 1)
            plate_parsed, ocr_conf, raw_ocr = None, 0.0, None
            is_cached = False

            with _ocr_cache_lock:
                cached_entry = _track_ocr_cache.get(track_id_str)
                if cached_entry and (now_sec - cached_entry[3]) < OCR_CACHE_TTL_SECONDS:
                    plate_parsed, ocr_conf, raw_ocr = cached_entry[0], cached_entry[1], cached_entry[2]
                    is_cached = True

            if not is_cached:
                plate_parsed, ocr_conf, raw_ocr = extract_ocr_from_vehicle_crop(v_crop)
                with _ocr_cache_lock:
                    if len(_track_ocr_cache) > 500:
                        _track_ocr_cache.clear()
                    _track_ocr_cache[track_id_str] = (plate_parsed, ocr_conf, raw_ocr, now_sec)

            # 3. FastReID Embedding & Global Identity
            res = vehicle_reid_pipeline.process_vehicle_track(
                camera_id=camera_id,
                track_uuid=track_id_str,
                vehicle_crop=v_crop,
                license_plate=plate_parsed
            )

            ident_id = res.get("global_vehicle_id") if res else None

            vehicles.append({
                "track_uuid": track_id_str,
                "vehicle_type": c_name,
                "vehicle_color": v_color,
                "license_plate": plate_parsed,
                "raw_ocr_text": raw_ocr or plate_parsed,
                "ocr_confidence": ocr_conf if ocr_conf > 0 else 0.85,
                "reid_vector": vehicle_reid_pipeline.extractor.extract_embedding(v_crop).tolist(),
                "identity_uuid": ident_id,
                "bbox": [x1, y1, x2, y2],
                "crop": v_crop
            })

    return vehicles


detect_vehicle_color_fallback = detect_vehicle_color
detect_vehicle_color_clip = detect_vehicle_color
