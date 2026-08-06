"""
Moondream 3 Cloud API captioner for Sybau VMS.

Drop-in replacement for Florence-2 scene captioning.
Uses the Moondream REST API (https://api.moondream.ai/v1/caption) with
a surveillance-specific prompt that explicitly asks for vehicle colors,
person clothing, license plates, and activity description.

Config (configs/models.json):
    "moondream": {
        "enabled": true,
        "invoke_every_n_frames": 30,
        "dispatch_interval_seconds": 0.5
    }

Env (.env):
    MOONDREAM_API_KEY=your_key_here
    MOONDREAM_MODEL=moondream3.1-9B-A2B
"""

from __future__ import annotations

import base64
import logging
import os
import time
import threading
import uuid
import queue
from collections import deque
from typing import Optional

import cv2
import httpx
import numpy as np

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
MOONDREAM_API_URL   = "https://api.moondream.ai/v1/query"
REQUEST_TIMEOUT_SEC = 30.0  # cloud API timeout per image


def _get_api_key() -> str:
    load_dotenv(override=True)
    return os.getenv("MOONDREAM_API_KEY", "")

def _get_model_name() -> str:
    return os.getenv("MOONDREAM_MODEL", "moondream3.1-9B-A2B")

MOONDREAM_PROMPT = (
    "You are analyzing a traffic surveillance frame. Generate a single detailed paragraph describing the current scene. "
    "Count every visible object accurately and describe only what is directly observable.\n\n"
    "Include:\n"
    "• Total vehicle count.\n"
    "• For every vehicle: type, color, approximate location (left/center/right, foreground/background), motion or parked status, "
    "travel direction if visible, and any roof cargo or carried load.\n"
    "• Number of motorcycles/scooters and whether they have one or more riders.\n"
    "• Number of pedestrians, their actions, and clothing colors.\n"
    "• Traffic conditions (light, moderate, heavy, congestion, stopped traffic).\n"
    "• Visible road markings, intersections, signals, barriers, sidewalks, fences, buildings, trees, utility poles, and advertisements.\n"
    "• Exact transcription of any readable license plates, shop names, signs, or banners. Never guess missing or blurry characters.\n"
    "• Road and environmental conditions including weather, lighting, shadows, and any obstructions.\n\n"
    "Return a single coherent paragraph containing only factual observations from the frame. "
    "Do not speculate about identities, intentions, speed, events before or after the frame, or hidden objects."
)


# ── Single-image API call (Single unified paragraph prompt) ───────────────────
def _call_moondream_api(image_data_uri: str, corr_id: str) -> str:
    """
    POST one image to Moondream cloud API with a single unified paragraph prompt.
    Returns a clean, detailed single-paragraph scene description.
    """
    api_key = _get_api_key()
    if not api_key or api_key == "your_key_here":
        raise RuntimeError("MOONDREAM_API_KEY not set in .env")

    client = _get_http_client()
    payload = {
        "model":     _get_model_name(),
        "image_url": image_data_uri,
        "question":  MOONDREAM_PROMPT,
        "stream":    False,
    }

    t0 = time.time()
    resp = client.post(MOONDREAM_API_URL, json=payload)
    elapsed = time.time() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"API HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    caption = (data.get("result") or data.get("answer") or data.get("caption") or "").strip()
    if not caption:
        raise RuntimeError(f"Empty response from API: {data}")

    logger.info(f"[Moondream] corr={corr_id} API took {elapsed:.2f}s → {len(caption)} chars")
    return caption


# ── Per-camera slot ───────────────────────────────────────────────────────────
class _MoondreamCameraSlot:
    __slots__ = ("pending", "pending_since", "last_captioned_at", "last_caption", "last_error")

    def __init__(self):
        self.pending          = False
        self.pending_since    = None
        self.last_captioned_at = None
        self.last_caption     = None
        self.last_error       = None


# ── Shared state ─────────────────────────────────────────────────────────────
_slots:    dict[str, _MoondreamCameraSlot] = {}
_slots_lock = threading.Lock()

# Async work queue: each item is (camera_id, frame_bytes_jpeg, yolo_summary, corr_id)
_work_queue: queue.Queue = queue.Queue(maxsize=64)

_stats = {
    "captioned":  0,
    "in_flight":  0,
    "errors":     0,
}
_stats_lock = threading.Lock()

# HTTP client — shared, connection-pooled
_http_client: Optional[httpx.Client] = None
_http_lock = threading.Lock()

def _get_http_client() -> httpx.Client:
    global _http_client
    api_key = _get_api_key()
    with _http_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.Client(
                timeout=REQUEST_TIMEOUT_SEC,
                headers={
                    "X-Moondream-Auth": api_key,
                    "Content-Type": "application/json",
                },
            )
        else:
            _http_client.headers["X-Moondream-Auth"] = api_key
    return _http_client


# ── Image encoding ────────────────────────────────────────────────────────────
def _encode_frame(frame: np.ndarray, max_dim: int = 1280) -> str:
    """
    Resize to max_dim on longest side, JPEG-encode, return data-URI base64 string.
    1280px gives maximum clarity for reading small text and small objects.
    """
    h, w = frame.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_LINEAR)
    # OpenCV imencode expects native BGR array. Passing frame directly preserves correct color channels in JPEG.
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


# ── Worker thread ─────────────────────────────────────────────────────────────
def _worker_thread():

    """Single background thread that drains the work queue sequentially."""
    logger.info("[Moondream] Worker thread started")
    while True:
        try:
            item = _work_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        if item is None:
            logger.info("[Moondream] Worker thread stopping")
            break

        camera_id, frame, yolo_summary, corr_id = item

        with _stats_lock:
            _stats["in_flight"] += 1

        try:
            image_uri = _encode_frame(frame)
            caption   = _call_moondream_api(image_uri, corr_id)

            # Build merged caption if YOLO summary is available
            if yolo_summary:
                full_caption = f"[YOLO]: {yolo_summary} | [Moondream]: {caption} | camera {camera_id}"
            else:
                full_caption = f"[Moondream]: {caption} | camera {camera_id}"

            # Persist to DB + Kafka
            _persist_caption(camera_id, full_caption, frame, corr_id)

            with _slots_lock:
                slot = _slots.get(camera_id)
                if slot:
                    import datetime
                    slot.last_caption      = full_caption
                    slot.last_captioned_at = datetime.datetime.now(datetime.timezone.utc)
                    slot.pending           = False
                    slot.last_error        = None

            with _stats_lock:
                _stats["captioned"] += 1

            logger.info(f"[Moondream] corr={corr_id} cam={camera_id} caption complete")

        except Exception as e:
            logger.error(f"[Moondream] corr={corr_id} cam={camera_id} ERROR: {e}", exc_info=True)
            with _slots_lock:
                slot = _slots.get(camera_id)
                if slot:
                    slot.pending    = False
                    slot.last_error = str(e)
            with _stats_lock:
                _stats["errors"] += 1
        finally:
            with _stats_lock:
                _stats["in_flight"] -= 1
            _work_queue.task_done()


# ── Persistence helper ────────────────────────────────────────────────────────
def _persist_caption(camera_id: str, full_caption: str, frame: np.ndarray, corr_id: str):
    """Write caption to Postgres SceneCaption table + Kafka captions topic."""
    try:
        import datetime, os, uuid
        from backend.database.connection import SessionLocal
        from backend.database.models import SceneCaption
        from backend.ai.embeddings.embedder import get_text_embedding
        from backend.messaging.kafka_client import event_client
        from backend.search.qdrant_utils import enqueue_qdrant_point


        snap_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "snapshots")
        )
        os.makedirs(snap_dir, exist_ok=True)


        vid      = str(uuid.uuid4())
        snap_path = os.path.join(snap_dir, f"{vid}.jpg")
        snap_url  = f"/api/v1/playback/snapshot/{vid}"
        _IST      = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now       = datetime.datetime.now(_IST)

        # Save snapshot asynchronously using shared persistent pool
        try:
            from backend.workers.ai_worker import save_snapshot_async
            save_snapshot_async(snap_path, frame)
        except Exception as snap_err:
            logger.warning(f"[Moondream] Snapshot write error cam={camera_id}: {snap_err}")


        # Embed caption text
        embedding = None
        try:
            embedding = get_text_embedding(full_caption)
        except Exception as e:
            logger.warning(f"[Moondream] Embedding error cam={camera_id}: {e}")

        # Write to Postgres
        with SessionLocal() as db:
            db_caption = SceneCaption(
                camera_id    = camera_id,
                caption      = full_caption,
                snapshot_url = snap_url,
                timestamp    = now,
            )
            db.add(db_caption)
            db.commit()

        # Index in Qdrant
        if embedding:
            enqueue_qdrant_point(vid, embedding, {
                "type":         "scene",
                "camera_id":    camera_id,
                "caption":      full_caption,
                "snapshot_url": snap_url,
                "timestamp":    now.isoformat(),
            })

        # Publish to Kafka
        try:
            event_client.publish_event("captions", {
                "camera_id": camera_id,
                "caption":   full_caption,
                "timestamp": now.isoformat(),
            })
        except Exception:
            pass

        # Evaluate active Custom Alert Rules against Moondream caption
        try:
            from backend.database.models import Alert, CustomAlertRule
            from backend.ai.behavior.custom_rules import custom_rule_evaluator

            with SessionLocal() as db:
                db_rules = db.query(CustomAlertRule).filter(CustomAlertRule.is_active == True).all()
                active_rules = [
                    {
                        "id": r.id,
                        "name": r.name,
                        "prompt": r.prompt,
                        "camera_id": r.camera_id,
                        "severity": r.severity,
                        "confidence_threshold": r.confidence_threshold,
                        "is_active": r.is_active,
                    }
                    for r in db_rules
                ]

                if active_rules:
                    custom_alerts = custom_rule_evaluator.evaluate_custom_rules(
                        {
                            "caption": full_caption,
                            "embedding": embedding,
                            "tracks": [],
                            "vehicles": []
                        },
                        active_rules,
                        camera_id
                    )

                    for alert in custom_alerts:
                        alert_conf = float(alert.get("confidence", 0.90))
                        db_alert = Alert(
                            camera_id=camera_id,
                            type=alert["type"],
                            message=alert["message"],
                            severity=alert.get("severity", "high"),
                            confidence=alert_conf,
                            timestamp=now,
                            latency_ms=150.0,
                            snapshot_url=snap_url
                        )
                        db.add(db_alert)
                        db.flush()

                        alert_payload = {
                            "id": db_alert.id,
                            "camera_id": camera_id,
                            "type": alert["type"],
                            "message": alert["message"],
                            "severity": alert.get("severity", "high"),
                            "confidence": alert_conf,
                            "timestamp": now.isoformat(),
                            "latency_ms": 150.0,
                            "snapshot_url": snap_url,
                        }
                        event_client.publish_event("alerts", alert_payload)
                        logger.info(f"[Moondream Alert] Triggered on {camera_id}: {alert['message']}")
                    db.commit()
        except Exception as alert_err:
            logger.warning(f"[Moondream] Custom alert evaluation note cam={camera_id}: {alert_err}")


    except Exception as e:
        logger.error(f"[Moondream] Persist error cam={camera_id}: {e}", exc_info=True)


# ── Public API ────────────────────────────────────────────────────────────────
_worker_thread_handle: Optional[threading.Thread] = None

def start_moondream_worker():
    """Call once at startup to launch the background worker thread."""
    global _worker_thread_handle
    if _worker_thread_handle and _worker_thread_handle.is_alive():
        return
    _worker_thread_handle = threading.Thread(
        target=_worker_thread, daemon=True, name="MoondreamWorker"
    )
    _worker_thread_handle.start()
    logger.info("[Moondream] Worker started")


def register_moondream_camera(camera_id: str):
    with _slots_lock:
        if camera_id not in _slots:
            _slots[camera_id] = _MoondreamCameraSlot()


def unregister_moondream_camera(camera_id: str):
    with _slots_lock:
        _slots.pop(camera_id, None)


def submit_moondream_caption(
    frame:        np.ndarray,
    camera_id:    str,
    yolo_summary: str = "",
    corr_id:      Optional[str] = None,
) -> bool:
    """
    Submit a frame for Moondream captioning. Non-blocking.
    Returns True if enqueued, False if camera already pending or queue full.
    """
    if corr_id is None:
        corr_id = uuid.uuid4().hex[:8]

    register_moondream_camera(camera_id)

    with _slots_lock:
        slot = _slots[camera_id]
        if slot.pending:
            return False  # camera already has an outstanding request
        import datetime
        slot.pending       = True
        slot.pending_since = datetime.datetime.now(datetime.timezone.utc)

    try:
        _work_queue.put_nowait((camera_id, frame.copy(), yolo_summary, corr_id))
        logger.info(f"[Moondream] corr={corr_id} cam={camera_id} ENQUEUED (qsize={_work_queue.qsize()})")
        return True
    except queue.Full:
        with _slots_lock:
            _slots[camera_id].pending = False
        logger.warning(f"[Moondream] corr={corr_id} cam={camera_id} queue FULL, dropped")
        return False


def get_moondream_stats() -> dict:
    with _slots_lock:
        cam_stats = {
            cid: {
                "pending":          s.pending,
                "pending_since":    s.pending_since.isoformat() if s.pending_since else None,
                "last_captioned_at": s.last_captioned_at.isoformat() if s.last_captioned_at else None,
                "last_caption":     s.last_caption,
                "last_error":       s.last_error,
            }
            for cid, s in _slots.items()
        }
    with _stats_lock:
        global_stats = dict(_stats)
    return {
        "queue":         _work_queue.qsize(),
        "in_flight":     global_stats["in_flight"],
        "captioned":     global_stats["captioned"],
        "errors":        global_stats["errors"],
        "model":         _get_model_name(),
        "camera_stats":  cam_stats,
    }
