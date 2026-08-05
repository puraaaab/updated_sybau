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
from ..database.models import Track, Face, Vehicle, Alert, Camera, Zone, AlertConfig, SceneCaption, CustomAlertRule
from ..messaging.kafka_client import event_client
from ..services.stream_manager import stream_manager
from ..ai.model_manager import model_manager
from ..search.qdrant_utils import qdrant_client_with_timeout, get_qdrant_client

# Shared ThreadPoolExecutor for writing snapshots asynchronously without blocking AI loop
_snapshot_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="SnapshotWriter")

def save_snapshot_async(snap_path: str, frame: np.ndarray):
    """Submits cv2.imwrite task to thread pool."""
    _snapshot_executor.submit(cv2.imwrite, snap_path, frame.copy())

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


latest_telemetry = {} # camera_id -> list of active tracks

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
        self.sampling_rate = 3.0 # Lower churn to reduce CPU/memory backlog while Florence is busy
        self._cached_zones = None
        self._cached_alerts_cfg = None
        self._last_cfg_fetch = 0.0
        self.CFG_CACHE_TTL = 1.0 # Refresh config every 1.0s for sub-second rule evaluation
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.thread.start()
        print(f"AI Worker started for Camera {self.camera_id}")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        try:
            from ..ai.captioning.captioner import unregister_florence_camera
            unregister_florence_camera(self.camera_id)
        except Exception:
            pass
        stream_manager.release_stream(self.camera_id)

    def _get_cached_config(self, db: Session):
        now = time.time()
        if self._cached_zones is None or (now - self._last_cfg_fetch) > self.CFG_CACHE_TTL:
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
                    "loitering": { "time_threshold_seconds": db_cfg.loitering_seconds },
                    "running": { "speed_threshold_pixels_per_second": db_cfg.running_speed_threshold },
                    "crowd": { "density_threshold": db_cfg.crowd_density_threshold }
                }
            else:
                self._cached_alerts_cfg = {}

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

        return self._cached_zones, self._cached_alerts_cfg

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

        # Register camera if missing in DB
        try:
            with SessionLocal() as db:
                cam_entry = db.query(Camera).filter(Camera.id == self.camera_id).first()
                if not cam_entry:
                    cameras_cfg = get_cameras()
                    cam_cfg = next((c for c in cameras_cfg if c["id"] == self.camera_id), {})
                    cam_entry = Camera(
                        id=self.camera_id,
                        name=cam_cfg.get("name", f"Camera {self.camera_id}"),
                        stream_url=self.stream_url,
                        status="connecting"
                    )
                    db.add(cam_entry)
                    db.commit()
        except Exception as cam_init_err:
            logger.warning(f"[{self.camera_id}] Camera registration check note: {cam_init_err}")

        interval = 0.2  # High Precision 5 FPS (0.2s sampling cadence)
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

        try:
            while self.running:
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

                try:
                    with SessionLocal() as db:
                        # Fetch zones and config from cache (refreshed every 1.0s)
                        zones, alerts_cfg = self._get_cached_config(db)

                        # Execute full AI inference pipeline on GPU
                        results = process_frame(frame, self.camera_id, zones, alerts_cfg, frame_idx)
                        frame_idx += 1

                    if frame_idx % 100 == 0:
                        import gc, torch
                        gc.collect()
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()

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

                    latest_telemetry[self.camera_id] = {
                        "tracks": clean_tracks,
                        "faces_count": len(results.get("faces", [])),
                        "vehicles_count": len(results.get("vehicles", [])),
                        "alerts_count": alerts_count,
                        "frame_idx": frame_idx,
                        "motion_status": motion_status,
                        "fps": current_fps,
                        "timestamp": datetime.datetime.now(_IST).isoformat()
                    }

                    from ..services.identity import GlobalIdentityManager

                    pending_snapshot_writes = []
                    pending_vector_index_ops = []
                    pending_caption_events = []
                    pending_alert_events = []

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

                            # AI-04 FIX: Compute normalized bbox center from real detection box
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

                            _now = datetime.datetime.now(_IST)  # IST timezone
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
                                db.add(db_track)
                            else:
                                existing_tr.last_seen = _now
                                existing_tr.speed = speed_val
                                existing_tr.path_history = path_json
                                existing_tr.last_bbox_x = round(float(bbox_cx), 4)
                                existing_tr.last_bbox_y = round(float(bbox_cy), 4)

                        # Batch faces
                        for face in results.get("faces", []):
                            resolved_identity = GlobalIdentityManager.get_or_create_face_identity(
                                face["track_uuid"], self.camera_id, face["embedding"]
                            )
                            db_face = Face(
                                track_uuid=face["track_uuid"],
                                label=resolved_identity,
                                embedding_id=face["embedding_id"],
                                timestamp=datetime.datetime.now(_IST)
                            )
                            db.add(db_face)

                            snap_path = os.path.join(snap_dir, f"{face['embedding_id']}.jpg")
                            pending_snapshot_writes.append((snap_path, frame))
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
                                    "timestamp": datetime.datetime.now(_IST).isoformat(),
                                }
                            ))

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

                        # Batch vehicles
                        for veh in results.get("vehicles", []):
                            resolved_identity = GlobalIdentityManager.get_or_create_vehicle_identity(
                                veh["track_uuid"], self.camera_id, veh["reid_vector"], veh["license_plate"]
                            )
                            db_veh = Vehicle(
                                track_uuid=veh["track_uuid"],
                                camera_id=self.camera_id,
                                license_plate=veh["license_plate"] or resolved_identity,
                                ocr_confidence=veh["ocr_confidence"],
                                vehicle_type=veh["vehicle_type"],
                                vehicle_color=veh.get("vehicle_color", "unknown"),
                                timestamp=datetime.datetime.now(_IST)
                            )
                            db.add(db_veh)

                            if veh["license_plate"]:
                                _plates_logger.info(
                                    f"CAMERA={self.camera_id} "
                                    f"PLATE={veh['license_plate']} "
                                    f"CONF={veh['ocr_confidence']:.2f} "
                                    f"TYPE={veh['vehicle_type']}"
                                )

                            plate_str = veh.get("license_plate")
                            if plate_str and str(plate_str).strip():
                                clean_p = str(plate_str).strip().upper().replace(" ", "")
                                vid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"VEHICLE_{clean_p}"))
                            else:
                                vid = str(uuid.uuid4())

                            snap_path = os.path.join(snap_dir, f"{vid}.jpg")
                            pending_snapshot_writes.append((snap_path, frame))
                            pending_vector_index_ops.append((
                                vid,
                                veh["reid_vector"],
                                {
                                    "type": "vehicle",
                                    "camera_id": self.camera_id,
                                    "license_plate": veh["license_plate"],
                                    "vehicle_type": veh.get("vehicle_type", "car"),
                                    "vehicle_color": veh.get("vehicle_color", "unknown"),
                                    "identity_uuid": resolved_identity,
                                    "track_uuid": veh["track_uuid"],
                                    "snapshot_url": f"/api/v1/playback/snapshot/{vid}",
                                    "timestamp": datetime.datetime.now(_IST).isoformat(),
                                }
                            ))

                        # Save detailed YOLO caption periodically and whenever Florence is disabled/not queued
                        florence_enabled = get_models().get("florence", {}).get("enabled", True)
                        florence_queued = results.get("florence_queued", False)
                        has_alerts = len(results.get("alerts", [])) > 0

                        should_save_caption = (
                            (not florence_enabled) or
                            (not florence_queued) or
                            has_alerts
                        )

                        if should_save_caption and results.get("caption") and results.get("embedding"):
                            vid = str(uuid.uuid4())
                            snap_path = os.path.join(snap_dir, f"{vid}.jpg")
                            pending_snapshot_writes.append((snap_path, frame))

                            snap_url = f"/api/v1/playback/snapshot/{vid}"
                            pending_vector_index_ops.append((
                                vid,
                                results["embedding"],
                                {
                                    "type": "scene",
                                    "camera_id": self.camera_id,
                                    "caption": results["caption"],
                                    "snapshot_url": snap_url,
                                    "timestamp": datetime.datetime.now(_IST).isoformat(),
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

                        # Batch alerts
                        for alert in results.get("alerts", []):
                            snap_id = str(uuid.uuid4())
                            snap_path = os.path.join(snap_dir, f"{snap_id}.jpg")
                            pending_snapshot_writes.append((snap_path, frame))

                            calc_latency = round((time.time() - start_time) * 1000.0, 2)
                            alert_conf = float(alert.get("confidence", 0.95))
                            db_alert = Alert(
                                camera_id=self.camera_id,
                                type=alert["type"],
                                message=alert["message"],
                                severity=alert["severity"],
                                confidence=alert_conf,
                                timestamp=datetime.datetime.now(_IST),
                                latency_ms=calc_latency,
                                snapshot_url=f"/api/v1/playback/snapshot/{snap_id}"
                            )
                            db.add(db_alert)
                            db.flush() # assign ID before commit

                            pending_alert_events.append({
                                "id": db_alert.id,
                                "camera_id": self.camera_id,
                                "type": alert["type"],
                                "message": alert["message"],
                                "severity": alert["severity"],
                                "confidence": alert_conf,
                                "timestamp": db_alert.timestamp.isoformat(),
                                "latency_ms": calc_latency,
                                "snapshot_url": db_alert.snapshot_url,
                            })

                        # Single batch commit for the frame
                        try:
                            db.commit()
                        except Exception as e:
                            logger.warning(f"[{self.camera_id}] DB commit error: {e}")
                            db.rollback()
                        else:
                            for snap_path, snap_frame in pending_snapshot_writes:
                                save_snapshot_async(snap_path, snap_frame)

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
