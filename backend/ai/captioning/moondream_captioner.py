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


_key_lock = threading.Lock()
_key_cursor = 0

def _get_next_api_key() -> tuple[str, int, int]:
    """
    Returns (api_key, key_index, total_keys) in round-robin sequence from MOONDREAM_API_KEYS (or MOONDREAM_API_KEY).
    Supports comma-separated keys in .env:
    MOONDREAM_API_KEYS=key1, key2, key3, key4
    """
    global _key_cursor
    load_dotenv(override=True)

    keys_str = os.getenv("MOONDREAM_API_KEYS", "").strip()
    if not keys_str:
        keys_str = os.getenv("MOONDREAM_API_KEY", "").strip()

    if not keys_str:
        return "", 0, 0

    raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    valid_keys = [k for k in raw_keys if k and not k.startswith("YOUR_MOONDREAM_KEY_") and k != "your_key_here"]

    target_list = valid_keys if valid_keys else raw_keys
    if not target_list:
        return "", 0, 0

    with _key_lock:
        idx = _key_cursor % len(target_list)
        key = target_list[idx]
        _key_cursor = (_key_cursor + 1) % len(target_list)
        return key, idx + 1, len(target_list)


def _get_model_name() -> str:
    return os.getenv("MOONDREAM_MODEL", "moondream3.1-9B-A2B")

MOONDREAM_PROMPT = (
    "You are analyzing a surveillance frame. Generate a single detailed paragraph describing the current scene. "
    "Count every visible object accurately and describe only what is directly observable.\n\n"
    "Include:\n"
    "• Total vehicle and person counts.\n"
    "• For every vehicle: type, color, location (left/center/right, foreground/background), motion or parked status.\n"
    "• Number of motorcycles/scooters and whether they have riders.\n"
    "• Number of pedestrians, their actions, and clothing colors.\n"
    "• Environment details: building entrances, doors, sidewalks, crosswalks, fences, trees, utility poles, advertisements.\n"
    "• Exact transcription of any clearly readable license plates, shop names, signs, or banners.\n\n"
    "Return a single coherent paragraph containing only positive factual observations from the frame. "
    "Do not state negative claims such as 'No license plates are legible' or 'No shop names are readable'. "
    "Do not speculate about identities, intentions, or events."
)


# ── Single-image API call (Round-Robin Multi-Key Rotation) ───────────────────
def _call_moondream_api(image_data_uri: str, corr_id: str) -> str:
    """
    POST one image to Moondream cloud API with round-robin API key rotation.
    Returns a clean, detailed single-paragraph scene description.
    """
    api_key, key_idx, total_keys = _get_next_api_key()
    if not api_key or api_key.startswith("YOUR_MOONDREAM_KEY_") or api_key == "your_key_here":
        raise RuntimeError("No valid Moondream API Key configured in MOONDREAM_API_KEYS / MOONDREAM_API_KEY in .env")

    headers = {
        "X-Moondream-Auth": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model":     _get_model_name(),
        "image_url": image_data_uri,
        "question":  MOONDREAM_PROMPT,
        "stream":    False,
    }

    t0 = time.time()
    with httpx.Client(timeout=REQUEST_TIMEOUT_SEC) as client:
        resp = client.post(MOONDREAM_API_URL, json=payload, headers=headers)
    elapsed = time.time() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"API HTTP {resp.status_code} (Key #{key_idx}/{total_keys}): {resp.text[:300]}")

    data = resp.json()
    caption = (data.get("result") or data.get("answer") or data.get("caption") or "").strip()
    if not caption:
        raise RuntimeError(f"Empty response from API (Key #{key_idx}/{total_keys}): {data}")

    logger.info(f"[Moondream] corr={corr_id} Key #{key_idx}/{total_keys} API took {elapsed:.2f}s → {len(caption)} chars")
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
    api_key, _, _ = _get_next_api_key()
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
def _encode_frame(frame: np.ndarray, max_dim: int = 1920) -> str:
    """
    Resize to max_dim on longest side, JPEG-encode, return data-URI base64 string.
    1920px (Full HD) with 95% JPEG quality ensures fine details, small objects, and signs are fully preserved.
    """
    h, w = frame.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_LINEAR)
    # OpenCV imencode expects native BGR array. Passing frame directly preserves correct color channels in JPEG.
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
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
            from backend.ai.captioning.caption_integrity import caption_integrity_validator
            image_uri = _encode_frame(frame)
            raw_caption = _call_moondream_api(image_uri, corr_id)

            # Strict 1-to-1 Image-to-Caption Integrity Verification
            is_valid, reason, envelope = caption_integrity_validator.validate_and_claim(
                image_id=corr_id,
                camera_id=camera_id,
                frame=frame,
                raw_caption=raw_caption
            )

            if not is_valid:
                logger.error(f"[Moondream INTEGRITY REJECTED] {reason}")
                with _slots_lock:
                    slot = _slots.get(camera_id)
                    if slot:
                        slot.pending = False
                        slot.last_error = reason
                with _stats_lock:
                    _stats["errors"] += 1
                continue

            # Integrity Check PASSED! Build merged caption
            if yolo_summary:
                full_caption = f"[YOLO]: {yolo_summary} | [Moondream]: {raw_caption} | camera {camera_id}"
            else:
                full_caption = f"[Moondream]: {raw_caption} | camera {camera_id}"

            # Persist to DB + Kafka using verified image_id
            _persist_caption(camera_id, full_caption, frame, corr_id)

            with _slots_lock:
                slot = _slots.get(camera_id)
                if slot:
                    from ...utils.timezone import get_ist_now
                    slot.last_caption      = full_caption
                    slot.last_captioned_at = get_ist_now()
                    slot.pending           = False
                    slot.last_error        = None

            with _stats_lock:
                _stats["captioned"] += 1

            logger.info(f"[Moondream INTEGRITY PASS] corr={corr_id} cam={camera_id} caption complete")

        except Exception as e:
            err_msg = str(e)
            if "No valid Moondream API Key" in err_msg:
                # Log clean warning once per minute without stack trace noise
                now_mono = time.monotonic()
                if not hasattr(_worker_thread, "_last_key_warn") or (now_mono - getattr(_worker_thread, "_last_key_warn", 0)) > 60:
                    logger.warning("[Moondream] MOONDREAM_API_KEY not configured in .env yet — cloud captioning paused until key is added.")
                    setattr(_worker_thread, "_last_key_warn", now_mono)
            else:
                logger.error(f"[Moondream] corr={corr_id} cam={camera_id} ERROR: {e}", exc_info=True)
            with _slots_lock:
                slot = _slots.get(camera_id)
                if slot:
                    slot.pending    = False
                    slot.last_error = err_msg
            with _stats_lock:
                _stats["errors"] += 1
        finally:
            with _stats_lock:
                _stats["in_flight"] -= 1
            _work_queue.task_done()


# ── Persistence helper ────────────────────────────────────────────────────────
def _persist_caption(camera_id: str, full_caption: str, frame: np.ndarray, corr_id: str):
    """Write caption to Postgres SceneCaption table + Kafka captions topic bound to image_id snapshot."""
    try:
        import datetime, os
        from backend.database.connection import SessionLocal
        from backend.database.models import SceneCaption
        from backend.ai.embeddings.embedder import get_text_embedding
        from backend.messaging.kafka_client import event_client
        from backend.search.qdrant_utils import enqueue_qdrant_point

        snap_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "snapshots")
        )
        os.makedirs(snap_dir, exist_ok=True)

        vid = corr_id if corr_id else f"img_{uuid.uuid4().hex[:12]}"
        snap_path = os.path.join(snap_dir, f"{vid}.jpg")
        snap_url  = f"/api/v1/playback/snapshot/{vid}"
        _IST      = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now       = datetime.datetime.now(_IST)

        # Save exact frame snapshot asynchronously bound to vid
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
    from backend.ai.captioning.caption_integrity import caption_integrity_validator
    image_id, envelope = caption_integrity_validator.create_envelope(
        frame=frame,
        camera_id=camera_id,
        yolo_summary=yolo_summary,
        custom_id=corr_id
    )

    register_moondream_camera(camera_id)

    with _slots_lock:
        slot = _slots[camera_id]
        if slot.pending:
            return False  # camera already has an outstanding request
        from ...utils.timezone import get_ist_now
        slot.pending       = True
        slot.pending_since = get_ist_now()

    try:
        _work_queue.put_nowait((camera_id, frame.copy(), yolo_summary, image_id))
        logger.info(f"[Moondream] image_id={image_id} cam={camera_id} ENQUEUED (qsize={_work_queue.qsize()})")
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
