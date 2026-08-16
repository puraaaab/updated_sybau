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
from typing import Optional, List

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
    "You are a forensic security vision intelligence AI analyzing live CCTV footage. "
    "Provide an exhaustive, highly detailed multi-sentence surveillance paragraph describing every authentic visual detail in this frame.\n\n"
    "Instructions:\n"
    "1. SCENE CONTEXT & ENVIRONMENT: Describe the complete spatial layout, road surface texture, lane dividers, curbs, sidewalks, buildings, trees/shrubs, streetlights, fences, weather conditions, shadows, and natural or artificial lighting.\n"
    "2. VEHICLES (only if actually present): Identify every distinct vehicle in the frame. Detail its vehicle type (car, SUV, sedan, auto-rickshaw, motorcycle, scooter, delivery truck, bus), precise paint color, exact position (left/center/right, foreground/background), orientation, and state (moving, stationary, parked).\n"
    "3. PEDESTRIANS & ATTIRE (only if actually present): State the exact count of people visible. For each person, describe their precise location, direction of movement, actions, upper garment style and color, lower garment style and color, and any accessories (backpack, handbag, helmet, umbrella).\n"
    "4. TEXT, PLATES & OVERLAYS: Transcribe any visible camera text, timestamps, watermarks, license plates, road signs, or shop boards verbatim.\n"
    "5. STRICT GROUNDING: Report ONLY what is physically visible. If the road or area is completely empty of vehicles and pedestrians, explicitly state that the roadway is clear and detail the quiet environment and pavement.\n\n"
    "Output a comprehensive, natural narrative paragraph packed with precise descriptive visual detail."
)


def _format_caption_as_paragraph(text: str) -> str:
    """Ensures caption is returned as a clean, fluent natural language paragraph rather than JSON."""
    if not text:
        return ""
    text = text.strip()

    # If text is JSON formatted, convert it into fluent paragraph prose
    if text.startswith("{") or text.startswith("["):
        try:
            import json
            obj = json.loads(text)
            sentences = []
            if isinstance(obj, dict):
                # Vehicles
                vehs = obj.get("VEHICLES")
                if vehs:
                    if isinstance(vehs, list):
                        for v in vehs:
                            if isinstance(v, dict):
                                col = str(v.get("color", "")).replace("unidentified", "").strip()
                                vtype = str(v.get("type", "vehicle")).replace("unidentified", "").strip()
                                make = str(v.get("make") or v.get("model") or "").replace("unidentified", "").strip()
                                pos = str(v.get("position", "")).replace("unidentified", "").strip()
                                stat = str(v.get("status", "")).replace("unidentified", "").strip()
                                label = f"{col} {make} {vtype}".strip() or "vehicle"
                                sentences.append(f"A {label} is {stat} on the {pos}." if pos or stat else f"A {label} is present.")
                    elif isinstance(vehs, dict):
                        col = str(vehs.get("color", "")).replace("unidentified", "").strip()
                        vtype = str(vehs.get("type", "vehicle")).replace("unidentified", "").strip()
                        make = str(vehs.get("make") or vehs.get("model") or "").replace("unidentified", "").strip()
                        pos = str(vehs.get("position", "")).replace("unidentified", "").strip()
                        stat = str(vehs.get("status", "")).replace("unidentified", "").strip()
                        label = f"{col} {make} {vtype}".strip() or "vehicle"
                        sentences.append(f"A {label} is {stat} on the {pos}." if pos or stat else f"A {label} is present.")

                # Two wheelers
                tw = obj.get("TWO_WHEELERS")
                if tw:
                    if isinstance(tw, list):
                        for t in tw:
                            if isinstance(t, dict):
                                col = str(t.get("color", "")).replace("unidentified", "").strip()
                                make = str(t.get("make") or t.get("model") or "two-wheeler").replace("unidentified", "").strip()
                                rc = t.get("rider_count")
                                riders = f" with {rc} riders" if rc else ""
                                sentences.append(f"A {col} {make}{riders} is visible.")
                    elif isinstance(tw, dict):
                        col = str(tw.get("color", "")).replace("unidentified", "").strip()
                        make = str(tw.get("make") or tw.get("model") or "two-wheeler").replace("unidentified", "").strip()
                        rc = tw.get("rider_count")
                        riders = f" with {rc} riders" if rc else ""
                        sentences.append(f"A {col} {make}{riders} is visible.")

                # Pedestrians
                peds = obj.get("PEDESTRIANS")
                if peds:
                    if isinstance(peds, dict):
                        cnt = peds.get("count") or (len(peds.get("positions", [])) if isinstance(peds.get("positions"), list) else None) or "Several"
                        cols = ", ".join(peds.get("clothing_colors", [])) if isinstance(peds.get("clothing_colors"), list) else ""
                        col_str = f" wearing {cols}" if cols else ""
                        sentences.append(f"{cnt} pedestrians{col_str} are active in the area.")
                    elif isinstance(peds, list):
                        sentences.append(f"{len(peds)} pedestrians are observed.")

                # Text / Plates
                txt = obj.get("TEXT")
                if txt:
                    if isinstance(txt, dict):
                        lp = str(txt.get("license_plate") or txt.get("plate") or "").replace("unidentified", "").strip()
                        loc = str(txt.get("location", "")).replace("unidentified", "").strip()
                        if lp:
                            sentences.append(f"License plate {lp} is visible {loc}." if loc else f"License plate {lp} is readable.")
                    elif isinstance(txt, str) and txt != "unidentified":
                        sentences.append(f"Visible text notes: {txt}.")

                # Environment
                env = obj.get("ENVIRONMENT")
                if isinstance(env, dict):
                    elems = [k for k, v in env.items() if v in (True, "yes", "visible", "present")]
                    if elems:
                        sentences.append(f"Surrounding environment features: {', '.join(elems)}.")

            if sentences:
                return " ".join(sentences).replace("  ", " ").strip()
        except Exception:
            pass

    # Clean whitespace and newlines
    cleaned = text.replace('\n\n', ' ').replace('\n', ' ').strip()

    # Multi-Delimiter Clause Splitting & Sub-Phrase Repetition Pruning
    import re
    raw_clauses = [c.strip() for c in re.split(r'[.!?;]\s*|\s*,\s*(?=[A-Z0-9]|one\b|two\b|a\b)', cleaned) if c.strip()]
    unique_clauses = []
    seen_normalized = set()
    phrase_counts = {}

    for clause in raw_clauses:
        norm = re.sub(r'[^a-z0-9]', '', clause.lower())
        if not norm or len(norm) < 3:
            continue
        if norm in seen_normalized:
            continue
        words = re.findall(r'\b[a-z]{2,}\b', clause.lower())
        is_repetitive = False
        if len(words) >= 3:
            for k in range(len(words) - 2):
                tri = f"{words[k]}_{words[k+1]}_{words[k+2]}"
                cnt = phrase_counts.get(tri, 0) + 1
                phrase_counts[tri] = cnt
                if cnt > 2:
                    is_repetitive = True
                    break
        if is_repetitive:
            continue
        seen_normalized.add(norm)
        formatted_clause = clause[0].upper() + clause[1:] if len(clause) > 1 else clause.upper()
        unique_clauses.append(formatted_clause)

    if unique_clauses:
        joined = ". ".join(unique_clauses).strip()
        if not joined.endswith("."):
            joined += "."
        cleaned = re.sub(r'\.+', '.', joined).replace(" .", ".")

    return cleaned


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

    # Format to guaranteed single natural language paragraph
    caption = _format_caption_as_paragraph(caption)

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
_work_queue: queue.Queue = queue.Queue(maxsize=256)

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
            save_snapshot_async(snap_path, frame, is_critical=True)
        except Exception as snap_err:
            logger.warning(f"[Moondream] Snapshot write error cam={camera_id}: {snap_err}")

        # Embed caption text
        embedding = None
        try:
            embedding = get_text_embedding(full_caption)
        except Exception as e:
            logger.warning(f"[Moondream] Embedding error cam={camera_id}: {e}")

        # Write to Database with retry
        for db_attempt in range(2):
            try:
                with SessionLocal() as db:
                    db_caption = SceneCaption(
                        camera_id    = camera_id,
                        caption      = full_caption,
                        snapshot_url = snap_url,
                        timestamp    = now,
                    )
                    db.add(db_caption)
                    db.commit()
                break
            except Exception as db_err:
                if db_attempt == 1:
                    logger.warning(f"[Moondream] DB persist note cam={camera_id}: {db_err}")

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
_worker_threads: List[threading.Thread] = []

def start_moondream_worker(num_workers: int = 4):
    """Launch concurrent background worker threads draining the Moondream queue across API keys."""
    global _worker_threads
    if _worker_threads and any(t.is_alive() for t in _worker_threads):
        return

    _worker_threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=_worker_thread, daemon=True, name=f"MoondreamWorker-{i+1}"
        )
        t.start()
        _worker_threads.append(t)
    logger.info(f"[Moondream] {len(_worker_threads)} concurrent workers started")


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
    Guarantees that the exact frame is bound to image_id and pre-saved immediately.
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

    # Save exact frame snapshot immediately on dispatch so snapshot always matches caption
    try:
        snap_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "snapshots")
        )
        os.makedirs(snap_dir, exist_ok=True)
        snap_path = os.path.join(snap_dir, f"{image_id}.jpg")
        from backend.workers.ai_worker import save_snapshot_async
        save_snapshot_async(snap_path, frame)
    except Exception as e:
        logger.warning(f"[Moondream] Snapshot pre-save note cam={camera_id}: {e}")

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
