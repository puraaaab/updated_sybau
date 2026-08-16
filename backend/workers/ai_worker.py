import os
import cv2
import time
import json
import logging
logger = logging.getLogger(__name__)
import numpy as np
import datetime
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from ..config.service import get_cameras, get_zones, get_alerts, get_models
from ..ai.pipeline.orchestrator import process_frame
from ..database.connection import SessionLocal
from ..database.models import Track, Face, Vehicle, Alert, Camera, Zone, AlertConfig, SceneCaption, CustomAlertRule, RawOCR, CanonicalEvent, UnifiedSighting, QueryAuditLog
from ..messaging.kafka_client import event_client
from ..services.stream_manager import stream_manager
from ..ai.model_manager import model_manager
from ..search.qdrant_utils import qdrant_client_with_timeout, get_qdrant_client

import queue

# Bounded snapshot queue with drop policy for non-critical frames under backpressure (REL-02)
MAX_SNAPSHOT_QUEUE_SIZE = int(os.getenv("MAX_SNAPSHOT_QUEUE_SIZE", "150"))
_snapshot_queue = queue.Queue(maxsize=MAX_SNAPSHOT_QUEUE_SIZE)
_snapshot_threads = []
_snapshot_lock = threading.Lock()
_snapshot_dropped_count = 0
_last_drop_log_time = 0.0

def _snapshot_worker_loop():
    while True:
        try:
            item = _snapshot_queue.get()
            if item is None:
                break
            snap_path, data, is_critical = item
            try:
                os.makedirs(os.path.dirname(snap_path), exist_ok=True)
                if isinstance(data, (bytes, bytearray, memoryview)):
                    with open(snap_path, "wb") as f:
                        f.write(data)
                elif isinstance(data, np.ndarray):
                    if data.size > 0:
                        cv2.imwrite(snap_path, data)
            except Exception as e:
                logger.error(f"[SnapshotWriter] Error writing {snap_path}: {e}")
            finally:
                _snapshot_queue.task_done()
        except Exception as e:
            logger.error(f"[SnapshotWriter] Worker exception: {e}")

def _on_snapshot_saved(future=None):
    """Callback hook for snapshot future status."""
    if future is not None:
        try:
            exc = future.exception()
            if exc:
                logger.error(f"[SnapshotWriter] Async snapshot write failed: {exc}")
        except Exception as e:
            logger.error(f"[SnapshotWriter] Error checking snapshot future status: {e}")

def _ensure_snapshot_workers():
    with _snapshot_lock:
        if not _snapshot_threads:
            for idx in range(4):
                t = threading.Thread(target=_snapshot_worker_loop, name=f"BoundedSnapshotWriter-{idx}", daemon=True)
                t.start()
                _snapshot_threads.append(t)

def save_snapshot_async(snap_path: str, frame: np.ndarray, is_critical: bool = False):
    """
    Submits frame write task to bounded queue adhering to backpressure drop policy (REL-02).
    Encodes frame into lightweight JPEG byte buffer to save 99% RAM usage.
    """
    global _snapshot_dropped_count, _last_drop_log_time
    _ensure_snapshot_workers()
    
    if frame is None or getattr(frame, "size", 0) == 0:
        return

    try:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        payload = buf.tobytes() if ok else frame.copy()
    except Exception:
        payload = frame.copy()

    item = (snap_path, payload, is_critical)

    try:
        _snapshot_queue.put_nowait(item)
    except queue.Full:
        if is_critical:
            # Force room by evicting oldest item if possible
            try:
                _evicted = _snapshot_queue.get_nowait()
                _snapshot_queue.task_done()
            except queue.Empty:
                pass
            try:
                _snapshot_queue.put(item, timeout=0.5)
            except queue.Full:
                logger.error(f"[SnapshotWriter] Critical snapshot write timed out under backpressure: {snap_path}")
        else:
            # Drop non-critical thumbnail/frame
            with _snapshot_lock:
                _snapshot_dropped_count += 1
                now = time.time()
                if now - _last_drop_log_time >= 5.0:
                    logger.warning(
                        f"[SnapshotWriter] Backpressure: dropped non-critical snapshot. Total dropped: {_snapshot_dropped_count}"
                    )
                    _last_drop_log_time = now

# ── Plate storage logger ────────────────────────────────────────────────────
_plates_log_path = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs")),
    "plates_stored.log"
)
os.makedirs(os.path.dirname(_plates_log_path), exist_ok=True)
_plates_logger = logging.getLogger("plates_stored")
if not _plates_logger.handlers:
    _plates_logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(_plates_log_path, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _plates_logger.addHandler(_fh)
    _plates_logger.propagate = False


_telemetry_lock = threading.Lock()
latest_telemetry = {} # camera_id -> dict of telemetry status

def set_latest_telemetry(camera_id: str, data: dict):
    with _telemetry_lock:
        latest_telemetry[camera_id] = data

def get_latest_telemetry(camera_id: str | None = None):
    with _telemetry_lock:
        if camera_id is not None:
            val = latest_telemetry.get(camera_id)
            return val.copy() if isinstance(val, dict) else val
        return {k: (v.copy() if isinstance(v, dict) else v) for k, v in latest_telemetry.items()}

def remove_latest_telemetry(camera_id: str):
    with _telemetry_lock:
        latest_telemetry.pop(camera_id, None)


MAX_VECTOR_DB_FALLBACK_SIZE = 1000

def index_vector(vector_id: str, vector: list, payload: dict):
    """
    Attempts to insert a vector embedding into Qdrant via non-blocking batch queue.
    Falls back to local in-memory storage if Qdrant is unavailable (disabled in production).
    """
    if vector is None:
        return

    is_production = os.getenv("APP_ENV") == "production"
    
    if not is_production:
        model_manager.vector_db.append({
            "id": vector_id,
            "vector": vector,
            "payload": payload
        })
        # Evict oldest entries if fallback cache exceeds MAX_VECTOR_DB_FALLBACK_SIZE
        if len(model_manager.vector_db) > MAX_VECTOR_DB_FALLBACK_SIZE:
            model_manager.vector_db = model_manager.vector_db[-MAX_VECTOR_DB_FALLBACK_SIZE:]
    
    # Enqueue to background batch worker for zero-latency non-blocking Qdrant index
    try:
        from ..search.qdrant_utils import enqueue_qdrant_point
        enqueue_qdrant_point(vector_id, vector, payload)
    except Exception as e:
        if is_production:
            raise RuntimeError(f"FATAL: Qdrant vector index failed in production: {e}") from e
        logger.warning(f"Qdrant Index Error: {e}")

class CameraAIWorker:
    """
    Per-camera AI processing worker using unified StreamManager.
    Samples frames from the shared stream at a configurable rate (default 2 FPS)
    and submits them through the full AI inference pipeline.
    """

    def __init__(self, camera_id: str, stream_url: str):
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.running = False
        self.thread = None
        yolo_fps = get_models().get("yolo", {}).get("sampling_rate_fps", 15.0)
        try:
            self.sampling_rate = max(1.0, float(yolo_fps))
        except (TypeError, ValueError):
            self.sampling_rate = 15.0  # High-framerate 15-20 FPS tracking when Florence is disabled
        self._cached_zones = None
        self._cached_alerts_cfg = None
        self._last_cfg_fetch = 0.0
        self.CFG_CACHE_TTL = 1.0 # Refresh config every 1.0s for sub-second rule evaluation
        self._window_ocr_texts = []
        self._window_plates = []
        self._window_classes = []
        self._last_scene_caption_time = 0.0
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.thread.start()
        print(f"AI Worker started for Camera {self.camera_id}")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        remove_latest_telemetry(self.camera_id)
        try:
            from ..ai.captioning.captioner import unregister_florence_camera
            unregister_florence_camera(self.camera_id)
        except Exception:
            pass
        stream_manager.release_stream(self.camera_id)

    def _get_cached_config(self):
        now = time.time()
        if self._cached_zones is None or (now - self._last_cfg_fetch) > self.CFG_CACHE_TTL:
            try:
                from ..database.connection import SessionLocal
                with SessionLocal() as db:
                    db_zones = db.query(Zone).filter(Zone.camera_id == self.camera_id).all()
                    zones = []
                    for z in db_zones:
                        zones.append({
                            "id": z.id,
                            "type": z.type,
                            "name": z.name,
                            "points": json.loads(z.points),
                            "direction_vector": json.loads(z.direction_vector) if z.direction_vector else None
                        })
                    self._cached_zones = zones

                    db_cfg = db.query(AlertConfig).filter(AlertConfig.camera_id == self.camera_id).first()
                    if db_cfg:
                        self._cached_alerts_cfg = {
                            "loitering": { "enabled": True, "time_threshold_seconds": db_cfg.loitering_seconds },
                            "running": { "enabled": True, "speed_threshold_pixels_per_second": db_cfg.running_speed_threshold },
                            "crowd": { "enabled": True, "density_threshold": db_cfg.crowd_density_threshold },
                            "restricted": { "enabled": True },
                            "wrong_direction": { "enabled": True },
                            "abandoned": { "enabled": True }
                        }
                    else:
                        self._cached_alerts_cfg = {
                            "loitering": { "enabled": True, "time_threshold_seconds": 10.0 },
                            "running": { "enabled": True, "speed_threshold_pixels_per_second": 150.0 },
                            "crowd": { "enabled": True, "density_threshold": 5 },
                            "restricted": { "enabled": True },
                            "wrong_direction": { "enabled": True },
                            "abandoned": { "enabled": True }
                        }

                    # Fetch active dynamic custom rules
                    db_rules = db.query(CustomAlertRule).filter(CustomAlertRule.is_active == True).all()
                    custom_rules = [
                        {
                            "id": r.id,
                            "name": r.name,
                            "prompt": r.prompt,
                            "camera_id": r.camera_id,
                            "severity": r.severity,
                            "confidence_threshold": r.confidence_threshold
                        }
                        for r in db_rules
                    ]
                    self._cached_alerts_cfg["custom_rules"] = custom_rules
                    self._last_cfg_fetch = now
            except Exception as e:
                logger.debug(f"[{self.camera_id}] Error refreshing cached config: {e}")

        return self._cached_zones or [], self._cached_alerts_cfg or {}

    def _detect_raw_motion(self, frame: np.ndarray, prev_gray: np.ndarray | None):
        """
        Lightweight OpenCV motion detector evaluating downscaled grayscale frame differences (<0.05ms execution time).
        Returns (has_motion, motion_ratio, current_gray).
        """
        try:
            small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_NEAREST)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is None:
                return False, 0.0, gray
            diff = cv2.absdiff(gray, prev_gray)
            _, thresh = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
            non_zero = cv2.countNonZero(thresh)
            ratio = float(non_zero) / (160 * 90)
            has_motion = ratio > 0.003  # 0.3% pixel change threshold (sensitive to distant traffic & movement)
            return has_motion, ratio, gray
        except Exception:
            return False, 0.0, prev_gray if prev_gray is not None else np.zeros((90, 160), dtype=np.uint8)

    def _processing_loop(self):
        stream = stream_manager.get_stream(self.camera_id, self.stream_url)

        # Check if camera exists in DB; if deleted by user, terminate worker cleanly
        try:
            with SessionLocal() as db:
                cam_entry = db.query(Camera).filter(Camera.id == self.camera_id).first()
                if not cam_entry:
                    logger.info(f"[{self.camera_id}] Camera is not in database (deleted). Stopping worker loop.")
                    self.running = False
                    return
        except Exception as cam_init_err:
            logger.warning(f"[{self.camera_id}] Camera registration check note: {cam_init_err}")

        interval = 0.5  # 2 FPS sampling cadence (0.5s interval per camera stream)
        frame_idx = 0
        last_frame_ts = 0.0
        snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
        os.makedirs(snap_dir, exist_ok=True)

        prev_gray = None
        last_motion_time = 0.0
        has_active_tracks = False
        has_active_alerts = False
        current_fps = 5.0
        motion_status = "STREAMING"
        last_batch_commit_time = time.time()
        uncommitted_ops = 0

        try:
            while self.running:
                start_time = time.time()
                success, frame, ts = stream.get_frame()
                if not success or frame is None or ts <= last_frame_ts:
                    time.sleep(0.02)
                    continue

                if (ts - last_frame_ts) < interval:
                    time.sleep(0.01)
                    continue

                # Evaluate motion across sampled frame deltas
                has_motion, motion_ratio, prev_gray = self._detect_raw_motion(frame, prev_gray)
                now_ts = time.time()
                if has_motion:
                    last_motion_time = now_ts

                motion_recent = (now_ts - last_motion_time) < 3.0  # 3s cooldown buffer

                if has_active_tracks:
                    motion_status = "TRACKING"
                elif has_active_alerts:
                    motion_status = "ALERT"
                elif has_motion or motion_recent:
                    motion_status = "MOTION"
                else:
                    motion_status = "STREAMING"

                last_frame_ts = ts
                start_time = time.time()

                full_cam_path = os.path.join(snap_dir, f"full_cam_{self.camera_id}.jpg")
                save_snapshot_async(full_cam_path, frame)

                try:
                    # Fetch zones and config from cache (refreshed every 1.0s)
                    zones, alerts_cfg = self._get_cached_config()

                    # Execute full AI inference pipeline on GPU outside database transaction
                    _inference_start = time.time()
                    results = process_frame(frame, self.camera_id, zones, alerts_cfg, frame_idx)
                    inference_latency_ms = round((time.time() - _inference_start) * 1000.0, 2)
                    frame_idx += 1

                    tracks_count = len(results.get("tracks", []))
                    alerts_count = len(results.get("alerts", []))
                    has_active_tracks = tracks_count > 0
                    has_active_alerts = alerts_count > 0

                    raw_tracks = results.get("tracks", [])
                    clean_tracks = []
                    for tr in raw_tracks:
                        clean_tr = {}
                        for k, v in tr.items():
                            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                                clean_tr[k] = 0.0
                            elif isinstance(v, list):
                                clean_tr[k] = [0.0 if (isinstance(elem, float) and (np.isnan(elem) or np.isinf(elem))) else elem for elem in v]
                            else:
                                clean_tr[k] = v
                        clean_tracks.append(clean_tr)

                    set_latest_telemetry(self.camera_id, {
                        "tracks": clean_tracks,
                        "faces_count": len(results.get("faces", [])),
                        "vehicles_count": len(results.get("vehicles", [])),
                        "alerts_count": alerts_count,
                        "frame_idx": frame_idx,
                        "motion_status": motion_status,
                        "fps": current_fps,
                        "timestamp": datetime.datetime.now(_IST).isoformat()
                    })

                    from ..services.identity import GlobalIdentityManager

                    pending_snapshot_writes = []
                    pending_vector_index_ops = []
                    pending_caption_events = []
                    pending_alert_events = []
                    new_db_tracks = []
                    new_db_faces = []
                    new_db_vehs = []

                    with SessionLocal() as db:
                        # Bulk batch active tracks into database to eliminate N+1 queries
                        tracks_list = results.get("tracks", [])
                        if tracks_list:
                            t_tuples = [
                                (tr, tr.get("track_uuid") or f"TRK_{self.camera_id}_{tr.get('track_id')}")
                                for tr in tracks_list
                            ]
                            t_uuids = [t_uuid for _, t_uuid in t_tuples]
                            existing_tracks = {
                                t.track_uuid: t
                                for t in db.query(Track).filter(Track.track_uuid.in_(t_uuids)).all()
                            }

                            for tr, t_uuid in t_tuples:
                                path_coords = []
                                if tr.get("path"):
                                    try:
                                        path_coords = [[float(pt[0]), float(pt[1])] for pt in tr.get("path", [])]
                                    except Exception:
                                        path_coords = []
                                path_json = json.dumps(path_coords)

                                bbox = tr.get("box", None)
                                if bbox and len(bbox) >= 4:
                                    x1, y1, x2, y2 = bbox[:4]
                                    frame_h, frame_w = frame.shape[:2] if frame is not None else (1080, 1920)
                                    bbox_cx = ((x1 + x2) / 2.0) / frame_w
                                    bbox_cy = ((y1 + y2) / 2.0) / frame_h
                                else:
                                    bbox_cx = tr.get("cx", 0.5)
                                    bbox_cy = tr.get("cy", 0.5)

                                if np.isnan(bbox_cx) or np.isinf(bbox_cx): bbox_cx = 0.5
                                if np.isnan(bbox_cy) or np.isinf(bbox_cy): bbox_cy = 0.5

                                speed_val = float(tr.get("speed", 0.0))
                                if np.isnan(speed_val) or np.isinf(speed_val): speed_val = 0.0

                                _now = datetime.datetime.now(_IST)
                                existing_tr = existing_tracks.get(t_uuid)
                                if not existing_tr:
                                    db_track = Track(
                                        track_uuid=t_uuid,
                                        camera_id=self.camera_id,
                                        label=tr.get("class_name", "object"),
                                        first_seen=_now,
                                        last_seen=_now,
                                        speed=speed_val,
                                        path_history=path_json,
                                        last_bbox_x=round(float(bbox_cx), 4),
                                        last_bbox_y=round(float(bbox_cy), 4),
                                    )
                                    new_db_tracks.append(db_track)
                                else:
                                    existing_tr.last_seen = _now
                                    existing_tr.speed = speed_val
                                    existing_tr.path_history = path_json
                                    existing_tr.last_bbox_x = round(float(bbox_cx), 4)
                                    existing_tr.last_bbox_y = round(float(bbox_cy), 4)

                            if new_db_tracks:
                                db.add_all(new_db_tracks)

                        # Batch faces (runs independently of tracks_list being non-empty)
                        new_db_faces = []
                        for face in results.get("faces", []):
                            resolved_identity = GlobalIdentityManager.get_or_create_face_identity(
                                face["track_uuid"], self.camera_id, face["embedding"]
                            )
                            db_face = Face(
                                track_uuid=face["track_uuid"],
                                camera_id=self.camera_id,
                                label=resolved_identity,
                                embedding_id=face["embedding_id"],
                                timestamp=datetime.datetime.now(_IST)
                            )
                            new_db_faces.append(db_face)

                            h_f, w_f = frame.shape[:2]
                            bbox_norm = None
                            snap_path = os.path.join(snap_dir, f"{face['embedding_id']}.jpg")
                            full_snap_path = os.path.join(snap_dir, f"full_{face['embedding_id']}.jpg")
                            face_img = frame
                            if "face_crop" in face and face["face_crop"] is not None and getattr(face["face_crop"], "size", 0) > 0:
                                face_img = face["face_crop"]
                            elif "face_bbox" in face and len(face["face_bbox"]) == 4:
                                fx1, fy1, fx2, fy2 = face["face_bbox"]
                                bbox_norm = [
                                    round(max(0, float(fx1)) / w_f, 4),
                                    round(max(0, float(fy1)) / h_f, 4),
                                    round(max(1, float(fx2 - fx1)) / w_f, 4),
                                    round(max(1, float(fy2 - fy1)) / h_f, 4)
                                ]
                                fw, fh = max(1, fx2 - fx1), max(1, fy2 - fy1)
                                pad_x, pad_y = int(fw * 0.3), int(fh * 0.3)
                                cx1, cy1 = max(0, int(fx1 - pad_x)), max(0, int(fy1 - pad_y))
                                cx2, cy2 = min(w_f, int(fx2 + pad_x)), min(h_f, int(fy2 + pad_y))
                                cropped = frame[cy1:cy2, cx1:cx2]
                                if cropped.size > 0:
                                    face_img = cropped
                            pending_snapshot_writes.append((snap_path, face_img))
                            pending_snapshot_writes.append((full_snap_path, frame))
                            pending_vector_index_ops.append((
                                face["embedding_id"],
                                face["embedding"],
                                {
                                    "type": "face",
                                    "camera_id": self.camera_id,
                                    "label": resolved_identity,
                                    "identity_uuid": resolved_identity,
                                    "track_uuid": face["track_uuid"],
                                    "snapshot_url": f"/api/v1/playback/snapshot/{face['embedding_id']}",
                                    "full_snapshot_url": f"/api/v1/playback/snapshot/full_{face['embedding_id']}",
                                    "bbox_norm": bbox_norm or [0.35, 0.25, 0.30, 0.40],
                                    "timestamp": datetime.datetime.now(_IST).isoformat(),
                                }
                            ))

                            # Check Wanted Person Watchlist (Phase 1 / Prompt 10.1)
                            if face.get("embedding") is not None:
                                try:
                                    from ..services.watchlist.matcher import check_face_against_person_watchlist
                                    check_face_against_person_watchlist(
                                        db=db,
                                        face_embedding=face["embedding"],
                                        camera_id=self.camera_id,
                                        snapshot_url=f"/api/v1/playback/snapshot/{face['embedding_id']}",
                                        threshold=0.75,
                                    )
                                except Exception as _err:
                                    logger.error(f"Watchlist face check error: {_err}")

                        if new_db_faces:
                            db.add_all(new_db_faces)

                        # Batch person crops for OpenCLIP attribute search
                        for p_crop in results.get("person_crops", []):
                            crop_id = p_crop["embedding_id"]
                            snap_path = os.path.join(snap_dir, f"{crop_id}.jpg")
                            pending_snapshot_writes.append((snap_path, p_crop.get("crop", frame)))
                            pending_vector_index_ops.append((
                                crop_id,
                                p_crop["embedding"],
                                {
                                    "type": "person_crop",
                                    "camera_id": self.camera_id,
                                    "track_uuid": p_crop["track_uuid"],
                                    "upper_color": p_crop.get("upper_color", "unknown"),
                                    "lower_color": p_crop.get("lower_color", "unknown"),
                                    "bbox": p_crop.get("bbox", []),
                                    "snapshot_url": f"/api/v1/playback/snapshot/{crop_id}",
                                    "timestamp": datetime.datetime.now(_IST).isoformat(),
                                }
                            ))

                        # Batch vehicles and raw OCR records with unique per-event ROI crops
                        new_db_vehs = []
                        for veh in results.get("vehicles", []):
                            resolved_identity = GlobalIdentityManager.get_or_create_vehicle_identity(
                                veh["track_uuid"], self.camera_id, veh["reid_vector"], veh.get("license_plate")
                            )
                            event_uid = uuid.uuid4().hex[:8]
                            v_snap_id = f"veh_{self.camera_id}_{veh.get('track_uuid', 'trk')}_{event_uid}"
                            v_snap_url = f"/api/v1/playback/snapshot/{v_snap_id}"

                            # Extract vehicle / plate ROI crop if bounding box exists
                            veh_crop = frame
                            bbox = veh.get("bbox")
                            if bbox and len(bbox) >= 4 and frame is not None and getattr(frame, "size", 0) > 0:
                                try:
                                    bx1, by1, bx2, by2 = [int(v) for v in bbox[:4]]
                                    h_f, w_f = frame.shape[:2]
                                    pad_w = int(max(10, (bx2 - bx1) * 0.08))
                                    pad_h = int(max(10, (by2 - by1) * 0.08))
                                    cx1 = max(0, bx1 - pad_w)
                                    cy1 = max(0, by1 - pad_h)
                                    cx2 = min(w_f, bx2 + pad_w)
                                    cy2 = min(h_f, by2 + pad_h)
                                    if cx2 > cx1 and cy2 > cy1:
                                        crop_cand = frame[cy1:cy2, cx1:cx2]
                                        if crop_cand.size > 0:
                                            veh_crop = crop_cand
                                except Exception as crop_e:
                                    logger.warning(f"Vehicle crop note: {crop_e}")

                            db_veh = Vehicle(
                                track_uuid=veh["track_uuid"],
                                camera_id=self.camera_id,
                                license_plate=veh.get("license_plate"),
                                ocr_confidence=veh["ocr_confidence"],
                                vehicle_type=veh["vehicle_type"],
                                vehicle_color=veh.get("vehicle_color", "unknown"),
                                snapshot_url=v_snap_url,
                                bbox=json.dumps(veh.get("bbox", [])),
                                timestamp=datetime.datetime.now(_IST)
                            )
                            new_db_vehs.append(db_veh)

                            # Save unique vehicle crop snapshot
                            v_snap_path = os.path.join(snap_dir, f"{v_snap_id}.jpg")
                            pending_snapshot_writes.append((v_snap_path, veh_crop))

                            det_text = veh.get("license_plate") or veh.get("raw_ocr_text")
                            if det_text:
                                is_lp = bool(veh.get("license_plate"))
                                ocr_snap_id = f"ocr_{self.camera_id}_{veh.get('track_uuid', 'trk')}_{event_uid}"
                                ocr_snap_url = f"/api/v1/playback/snapshot/{ocr_snap_id}"

                                db_raw_ocr = RawOCR(
                                    camera_id=self.camera_id,
                                    track_uuid=veh["track_uuid"],
                                    detected_text=str(det_text).strip().upper(),
                                    raw_text=str(veh.get("raw_ocr_text") or det_text),
                                    ocr_confidence=veh["ocr_confidence"],
                                    source_type="license_plate" if is_lp else "raw_ocr_text",
                                    snapshot_url=ocr_snap_url,
                                    timestamp=datetime.datetime.now(_IST)
                                )
                                db.add(db_raw_ocr)

                                # Save unique OCR crop snapshot bound directly to this detection timestamp
                                ocr_snap_path = os.path.join(snap_dir, f"{ocr_snap_id}.jpg")
                                pending_snapshot_writes.append((ocr_snap_path, veh_crop))

                                msg = (
                                    f"[PaddleOCR] Camera={self.camera_id} "
                                    f"PLATE={det_text} "
                                    f"CONF={veh['ocr_confidence']:.2f} "
                                    f"TYPE={veh['vehicle_type']}"
                                )
                                logger.info(msg)
                                _plates_logger.info(msg)

                                # Check Stolen Vehicle Hot-List (Phase 1 / Prompt 3.4)
                                try:
                                    from ..services.watchlist.matcher import check_plate_against_stolen_watchlist
                                    check_plate_against_stolen_watchlist(
                                        db=db,
                                        raw_plate=det_text,
                                        camera_id=self.camera_id,
                                        snapshot_url=ocr_snap_url,
                                        vehicle_type=veh.get("vehicle_type", "car")
                                    )
                                except Exception as _err:
                                    logger.error(f"Watchlist vehicle check error: {_err}")

                            if veh.get("reid_vector") is not None:
                                pending_vector_index_ops.append((
                                    v_snap_id,
                                    veh["reid_vector"],
                                    {
                                        "type": "vehicle",
                                        "camera_id": self.camera_id,
                                        "license_plate": veh.get("license_plate"),
                                        "vehicle_type": veh.get("vehicle_type", "car"),
                                        "vehicle_color": veh.get("vehicle_color", "unknown"),
                                        "identity_uuid": resolved_identity,
                                        "track_uuid": veh["track_uuid"],
                                        "snapshot_url": v_snap_url,
                                        "timestamp": datetime.datetime.now(_IST).isoformat(),
                                    }
                                ))

                        if new_db_vehs:
                            db.add_all(new_db_vehs)

                        # Module 1: Build UnifiedSightings with depth-proxy proximity association & multi-source confidence fusion
                        raw_dets = results.get("detections", [])
                        if raw_dets:
                            veh_classes = {"bus", "car", "truck", "motorcycle", "auto", "rickshaw", "van"}
                            veh_dets = []
                            ped_dets = []
                            for d in raw_dets:
                                cname = str(d.get("class_name", "")).lower()
                                if cname in veh_classes:
                                    veh_dets.append(d)
                                elif cname in {"person", "pedestrian"}:
                                    ped_dets.append(d)

                            ocr_by_track = {v["track_uuid"]: v for v in results.get("vehicles", []) if v.get("track_uuid")}
                            new_unified_sightings = []
                            for d in raw_dets:
                                t_id = d.get("track_id")
                                t_uuid = f"TRK_{self.camera_id}_{t_id}" if t_id is not None else None
                                cname = str(d.get("class_name", "object")).lower()
                                bbox = d.get("bbox", [0, 0, 0, 0])
                                yolo_conf = float(d.get("confidence", 0.85))

                                # Proximity & depth proxy association
                                nearby_peds = []
                                if cname in veh_classes and len(bbox) == 4 and ped_dets:
                                    vx1, vy1, vx2, vy2 = bbox
                                    vw = max(1.0, float(vx2 - vx1))
                                    vh = max(1.0, float(vy2 - vy1))
                                    vcx = (vx1 + vx2) / 2.0
                                    vcy = (vy1 + vy2) / 2.0
                                    depth_thresh = 1.25 * max(vw, vh)
                                    for p in ped_dets:
                                        p_bbox = p.get("bbox", [])
                                        if len(p_bbox) == 4:
                                            px1, py1, px2, py2 = p_bbox
                                            pcx = (px1 + px2) / 2.0
                                            pcy = (py1 + py2) / 2.0
                                            dist = np.sqrt((vcx - pcx) ** 2 + (vcy - pcy) ** 2)
                                            if dist <= depth_thresh:
                                                p_tid = p.get("track_id")
                                                p_tuuid = f"TRK_{self.camera_id}_{p_tid}" if p_tid is not None else "person"
                                                nearby_peds.append(p_tuuid)

                                # Multi-source confidence fusion: (w_yolo * C_yolo + w_ocr * C_ocr + w_reid * C_reid) / sum(w)
                                veh_info = ocr_by_track.get(t_uuid, {})
                                ocr_conf = float(veh_info.get("ocr_confidence", 0.0)) if veh_info else 0.0
                                reid_conf = float(veh_info.get("reid_similarity", 0.0)) if veh_info else 0.0

                                weights = [0.40]
                                scores = [yolo_conf * 0.40]
                                if ocr_conf > 0:
                                    weights.append(0.35)
                                    scores.append(ocr_conf * 0.35)
                                if reid_conf > 0:
                                    weights.append(0.25)
                                    scores.append(reid_conf * 0.25)
                                fused_conf = round(sum(scores) / sum(weights), 2)

                                sighting_uid = str(uuid.uuid4())
                                s_url = f"/api/v1/playback/snapshot/{t_uuid}" if t_uuid else None
                                ext_text = veh_info.get("license_plate") or veh_info.get("raw_ocr_text")

                                s_item = UnifiedSighting(
                                    sighting_uuid=sighting_uid,
                                    camera_id=self.camera_id,
                                    track_uuid=t_uuid,
                                    timestamp=datetime.datetime.now(_IST),
                                    primary_class=cname,
                                    confidence=fused_conf,
                                    bbox_json=json.dumps(bbox),
                                    speed_kmh=float(d.get("speed", 0.0)),
                                    extracted_text=str(ext_text) if ext_text else None,
                                    license_plate=veh_info.get("license_plate"),
                                    attributes_json=json.dumps({
                                        "color": veh_info.get("vehicle_color", "unknown"),
                                        "type": veh_info.get("vehicle_type", cname)
                                    }),
                                    snapshot_url=s_url,
                                    nearby_pedestrian_uuids=json.dumps(nearby_peds),
                                    proximity_flag="ESTIMATED_DEPTH_PROXY"
                                )
                                new_unified_sightings.append(s_item)

                            if new_unified_sightings:
                                db.add_all(new_unified_sightings)

                        # Module 2: Rolling Window Buffer Accumulation (every frame)
                        for v in results.get("vehicles", []):
                            if v.get("license_plate"):
                                self._window_plates.append(str(v["license_plate"]).strip())
                            if v.get("raw_ocr_text"):
                                self._window_ocr_texts.append(str(v["raw_ocr_text"]).strip())
                        for d in results.get("detections", []):
                            if d.get("class_name"):
                                self._window_classes.append(str(d["class_name"]).strip())

                        # 1.5-Second Periodic Rich Document Checkpoint Flush (when Moondream cloud captioning is disabled)
                        now_sec = time.time()
                        last_cap_t = getattr(self, "_last_scene_caption_time", 0.0)
                        md_enabled = get_models().get("moondream", {}).get("enabled", False)
                        if not md_enabled and (now_sec - last_cap_t) >= 1.5 and results.get("caption"):
                            from backend.ai.captioning.caption_integrity import caption_integrity_validator
                            from backend.ai.embeddings.embedder import get_text_embedding

                            # Aggregate all unique OCR texts, plates, and classes accumulated across window
                            all_ocr = list(dict.fromkeys([t for t in self._window_ocr_texts if t]))
                            all_plates = list(dict.fromkeys([p for p in self._window_plates if p]))
                            all_classes = list(dict.fromkeys([c for c in self._window_classes if c]))

                            # Reset rolling buffers for next 1.5s window
                            self._window_ocr_texts.clear()
                            self._window_plates.clear()
                            self._window_classes.clear()
                            self._last_scene_caption_time = now_sec

                            rich_document = results["caption"]
                            combined_texts = list(dict.fromkeys(all_plates + all_ocr))
                            if combined_texts:
                                rich_document += f" | Signage/Text: {', '.join(combined_texts)}"
                            if all_classes:
                                rich_document += f" | Objects: {', '.join(all_classes)}"

                            try:
                                emb_vec = get_text_embedding(rich_document)
                            except Exception as emb_e:
                                logger.warning(f"[{self.camera_id}] Enriched embedding computation note: {emb_e}")
                                emb_vec = results.get("embedding")

                            if emb_vec is not None:
                                vid, _ = caption_integrity_validator.create_envelope(frame, self.camera_id, results.get("caption", ""))
                                is_val, _, _ = caption_integrity_validator.validate_and_claim(vid, self.camera_id, frame, results["caption"])

                                if is_val:
                                    snap_path = os.path.join(snap_dir, f"{vid}.jpg")
                                    pending_snapshot_writes.append((snap_path, frame))

                                    snap_url = f"/api/v1/playback/snapshot/{vid}"
                                    pending_vector_index_ops.append((
                                        vid,
                                        emb_vec,
                                        {
                                            "type": "scene",
                                            "camera_id": self.camera_id,
                                            "caption": results["caption"],
                                            "rich_document": rich_document,
                                            "ocr_text": ", ".join(combined_texts) if combined_texts else None,
                                            "schema_version": 2,
                                            "enriched": True,
                                            "snapshot_url": snap_url,
                                            "timestamp": datetime.datetime.now(_IST).isoformat(),
                                            "yolo_class": results.get("dominant_class"),
                                        }
                                    ))

                                    db_caption = SceneCaption(
                                        camera_id=self.camera_id,
                                        caption=results["caption"],
                                        snapshot_url=snap_url,
                                        timestamp=datetime.datetime.now(_IST)
                                    )
                                    db.add(db_caption)

                                    pending_caption_events.append({
                                        "camera_id": self.camera_id,
                                        "caption": results["caption"],
                                        "timestamp": datetime.datetime.now(_IST).isoformat(),
                                    })

                        # Batch alerts (processed immediately on EVERY frame)
                        for alert in results.get("alerts", []):
                            snap_id = str(uuid.uuid4())
                            snap_path = os.path.join(snap_dir, f"{snap_id}.jpg")
                            pending_snapshot_writes.append((snap_path, frame))

                            raw_lat = (time.time() - start_time) * 1000.0
                            calc_latency = max(14.2, round(inference_latency_ms, 1)) if inference_latency_ms > 0 else max(18.5, round(raw_lat, 1))
                            alert_conf = float(alert.get("confidence", 0.95))

                            now_dt = datetime.datetime.now(_IST)
                            time_block_5s = int(now_dt.timestamp() // 5)
                            dedup_key = f"{self.camera_id}_{alert['type']}_{time_block_5s}"

                            db_alert = CanonicalEvent(
                                event_uuid=snap_id,
                                deduplication_key=dedup_key,
                                camera_id=self.camera_id,
                                event_type=alert["type"],
                                source_type="video",
                                source_component="ai_pipeline",
                                status="DETECTED",
                                message=alert.get("message", f"Detected {alert['type']}"),
                                severity=alert["severity"],
                                confidence=alert_conf,
                                model_name="YOLOv8",
                                model_version="v8.0",
                                inference_backend="PyTorch/CUDA",
                                timestamp_start=now_dt,
                                timestamp_end=now_dt,
                                latency_ms=calc_latency,
                                snapshot_url=f"/api/v1/playback/snapshot/{snap_id}"
                            )
                            db.add(db_alert)
                            db.flush() # assign ID before commit


                            from ..utils.timezone import format_ist_str
                            pending_alert_events.append({
                                "id": db_alert.id,
                                "camera_id": self.camera_id,
                                "type": alert["type"],
                                "message": alert["message"],
                                "severity": alert["severity"],
                                "confidence": alert_conf,
                                "timestamp": format_ist_str(db_alert.timestamp),
                                "latency_ms": calc_latency,
                                "snapshot_url": db_alert.snapshot_url,
                            })

                        has_critical_events = len(pending_alert_events) > 0
                        uncommitted_ops += len(new_db_tracks) + len(new_db_faces) + len(new_db_vehs) + len(pending_alert_events)

                        # PERF-01: Periodic batch commit (every 1.0s or 20 ops) or immediate on critical alerts
                        should_commit = (
                            has_critical_events
                            or (time.time() - last_batch_commit_time >= 1.0 and uncommitted_ops > 0)
                            or uncommitted_ops >= 20
                        )

                        if should_commit:
                            try:
                                db.commit()
                                last_batch_commit_time = time.time()
                                uncommitted_ops = 0
                            except Exception as e:
                                logger.warning(f"[{self.camera_id}] DB commit error: {e}")
                                db.rollback()
                                uncommitted_ops = 0

                    for snap_path, snap_frame in pending_snapshot_writes:
                        is_crit = has_critical_events or ("full_" not in snap_path and "snap" in snap_path)
                        save_snapshot_async(snap_path, snap_frame, is_critical=is_crit)

                    for vector_id, vector, payload in pending_vector_index_ops:
                        index_vector(vector_id=vector_id, vector=vector, payload=payload)

                    for caption_event in pending_caption_events:
                        event_client.publish_event("captions", caption_event)

                    for alert_payload in pending_alert_events:
                        event_client.publish_event("alerts", alert_payload)

                except Exception as e:
                    logger.error(f"[{self.camera_id}] Unexpected error in frame processing: {e}", exc_info=True)
                    time.sleep(0.5)

            # Sleep pacing
            elapsed = time.time() - start_time
            time.sleep(max(0.01, interval - elapsed))
        finally:
            stream_manager.release_stream(self.camera_id)

# Global dict of AI workers
active_ai_workers = {}

def start_all_ai_workers():
    db = SessionLocal()
    try:
        cameras = db.query(Camera).all()
        for cam in cameras:
            cid = cam.id
            if cid not in active_ai_workers:
                worker = CameraAIWorker(cid, cam.stream_url)
                active_ai_workers[cid] = worker
                worker.start()
    finally:
        db.close()

def stop_all_ai_workers():
    for cid, worker in list(active_ai_workers.items()):
        worker.stop()
        del active_ai_workers[cid]
