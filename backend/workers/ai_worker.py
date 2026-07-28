import os
import cv2
import time
import json
import logging
logger = logging.getLogger(__name__)
import numpy as np
import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from ..config.service import get_cameras, get_zones, get_alerts
from ..ai.pipeline.orchestrator import process_frame
from ..database.connection import SessionLocal
from ..database.models import Track, Face, Vehicle, Alert, Camera, Zone, AlertConfig, SceneCaption
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
        self.sampling_rate = 2.0 # 2 FPS
        self._cached_zones = None
        self._cached_alerts_cfg = None
        self._last_cfg_fetch = 0.0
        self.CFG_CACHE_TTL = 10.0 # Refresh config every 10s
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.thread.start()
        print(f"AI Worker started for Camera {self.camera_id}")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
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

        try:
            with SessionLocal() as db:
                # Register camera if missing in DB
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

                interval = 0.5
                frame_idx = 0
                last_frame_ts = 0.0
                snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
                os.makedirs(snap_dir, exist_ok=True)

                prev_gray = None
                last_motion_time = 0.0
                has_active_tracks = False
                has_active_alerts = False
                current_fps = 2.0
                motion_status = "STREAMING"

                while self.running:
                    success, frame, ts = stream.get_frame()
                    if not success or frame is None or ts <= last_frame_ts:
                        time.sleep(0.02)
                        continue

                    # Rate limit sampling to constant 2.0 FPS (0.5s interval)
                    if (ts - last_frame_ts) < interval:
                        time.sleep(0.01)
                        continue

                    # Evaluate motion across sampled frame deltas
                    has_motion, motion_ratio, prev_gray = self._detect_raw_motion(frame, prev_gray)
                    now_ts = time.time()
                    if has_motion:
                        last_motion_time = now_ts

                    motion_recent = (now_ts - last_motion_time) < 3.0  # 3s cooldown buffer

                    # Dynamic Status Decision (constant 2.0 FPS capture rate)
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
                        # Fetch zones and config from cache (refreshed every 10s)
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

                        latest_telemetry[self.camera_id] = {
                            "tracks": results.get("tracks", []),
                            "faces_count": len(results.get("faces", [])),
                            "vehicles_count": len(results.get("vehicles", [])),
                            "alerts_count": alerts_count,
                            "frame_idx": frame_idx,
                            "motion_status": motion_status,
                            "fps": current_fps,
                            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }

                        from ..services.identity import GlobalIdentityManager

                        # Batch faces
                        for face in results.get("faces", []):
                            resolved_identity = GlobalIdentityManager.get_or_create_face_identity(
                                face["track_uuid"], self.camera_id, face["embedding"]
                            )
                            db_face = Face(
                                track_uuid=face["track_uuid"],
                                label=resolved_identity,
                                embedding_id=face["embedding_id"],
                                timestamp=datetime.datetime.utcnow()
                            )
                            db.add(db_face)

                            snap_path = os.path.join(snap_dir, f"{face['embedding_id']}.jpg")
                            save_snapshot_async(snap_path, frame)

                            index_vector(
                                vector_id=face["embedding_id"],
                                vector=face["embedding"],
                                payload={
                                    "type": "face",
                                    "camera_id": self.camera_id,
                                    "label": resolved_identity,
                                    "identity_uuid": resolved_identity,
                                    "track_uuid": face["track_uuid"],
                                    "snapshot_url": f"/api/v1/playback/snapshot/{face['embedding_id']}",
                                    "timestamp": datetime.datetime.utcnow().isoformat()
                                }
                            )

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
                                timestamp=datetime.datetime.utcnow()
                            )
                            db.add(db_veh)

                            if veh["license_plate"]:
                                _plates_logger.info(
                                    f"CAMERA={self.camera_id} "
                                    f"PLATE={veh['license_plate']} "
                                    f"CONF={veh['ocr_confidence']:.2f} "
                                    f"TYPE={veh['vehicle_type']}"
                                )

                            vid = str(uuid.uuid4())
                            snap_path = os.path.join(snap_dir, f"{vid}.jpg")
                            save_snapshot_async(snap_path, frame)

                            index_vector(
                                vector_id=vid,
                                vector=veh["reid_vector"],
                                payload={
                                    "type": "vehicle",
                                    "camera_id": self.camera_id,
                                    "license_plate": veh["license_plate"],
                                    "vehicle_type": veh.get("vehicle_type", "car"),
                                    "vehicle_color": veh.get("vehicle_color", "unknown"),
                                    "identity_uuid": resolved_identity,
                                    "track_uuid": veh["track_uuid"],
                                    "snapshot_url": f"/api/v1/playback/snapshot/{vid}",
                                    "timestamp": datetime.datetime.utcnow().isoformat()
                                }
                            )

                        # Save caption embedding
                        if results.get("caption") and results.get("embedding"):
                            vid = str(uuid.uuid4())
                            snap_path = os.path.join(snap_dir, f"{vid}.jpg")
                            save_snapshot_async(snap_path, frame)

                            snap_url = f"/api/v1/playback/snapshot/{vid}"
                            index_vector(
                                vector_id=vid,
                                vector=results["embedding"],
                                payload={
                                    "type": "scene",
                                    "camera_id": self.camera_id,
                                    "caption": results["caption"],
                                    "snapshot_url": snap_url,
                                    "timestamp": datetime.datetime.utcnow().isoformat()
                                }
                            )

                            db_caption = SceneCaption(
                                camera_id=self.camera_id,
                                caption=results["caption"],
                                snapshot_url=snap_url,
                                timestamp=datetime.datetime.utcnow()
                            )
                            db.add(db_caption)
                            try:
                                db.commit()
                            except Exception as db_err:
                                logger.warning(f"[{self.camera_id}] SceneCaption commit warning: {db_err}")
                                db.rollback()

                            event_client.publish_event("captions", {
                                "camera_id": self.camera_id,
                                "caption": results["caption"],
                                "timestamp": datetime.datetime.utcnow().isoformat()
                            })

                        # Batch alerts
                        for alert in results.get("alerts", []):
                            snap_id = str(uuid.uuid4())
                            snap_path = os.path.join(snap_dir, f"{snap_id}.jpg")
                            save_snapshot_async(snap_path, frame)

                            calc_latency = round((time.time() - start_time) * 1000.0, 2)
                            db_alert = Alert(
                                camera_id=self.camera_id,
                                type=alert["type"],
                                message=alert["message"],
                                severity=alert["severity"],
                                timestamp=datetime.datetime.utcnow(),
                                latency_ms=calc_latency,
                                snapshot_url=f"/api/v1/playback/snapshot/{snap_id}"
                            )
                            db.add(db_alert)
                            db.flush() # assign ID before commit

                            alert_payload = {
                                "id": db_alert.id,
                                "camera_id": self.camera_id,
                                "type": alert["type"],
                                "message": alert["message"],
                                "severity": alert["severity"],
                                "timestamp": db_alert.timestamp.isoformat(),
                                "latency_ms": calc_latency,
                                "snapshot_url": db_alert.snapshot_url
                            }
                            event_client.publish_event("alerts", alert_payload)

                        # Single batch commit for the frame
                        try:
                            db.commit()
                        except Exception as e:
                            logger.warning(f"[{self.camera_id}] DB commit error: {e}")
                            db.rollback()

                    except Exception as e:
                        logger.error(f"[{self.camera_id}] Unexpected error in frame processing: {e}", exc_info=True)
                        db.rollback()
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
