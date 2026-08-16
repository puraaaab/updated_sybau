import logging
import random
import queue
import time
import uuid
import threading
import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import torch
from PIL import Image

from ...config.service import get_models
from ..model_manager import model_manager
from ...utils.timezone import IST_TZ

# ---------------------------------------------------------------------------
# Dedicated CUDA stream for Florence — YOLO runs on default stream (stream 0),
# Florence runs on stream 1 so both can be pipelined by the GPU scheduler.
# Falls back to None (default stream) if CUDA is unavailable or stream creation
# fails — behaviour is correct either way, just without parallelism.
# ---------------------------------------------------------------------------
try:
    _florence_cuda_stream: torch.cuda.Stream | None = (
        torch.cuda.Stream() if torch.cuda.is_available() else None
    )
    if _florence_cuda_stream is not None:
        logger_tmp = logging.getLogger(__name__)
        logger_tmp.info("[Florence] Dedicated CUDA stream created for parallel inference.")
except Exception as _stream_exc:
    _florence_cuda_stream = None  # fallback: default stream, no parallelism loss

_persister_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="Florence_Persister")

logger = logging.getLogger(__name__)

MOCK_DESCRIPTIONS = [
    "A person with a backpack walking slowly near the entrance.",
    "A white car entering the loading dock area.",
    "Two people chatting near the office doorway.",
    "A person carrying a cardboard box heading toward the exit.",
    "A blue sedan parked near the pedestrian walkway.",
    "An operator walking past the camera range."
]

CAPTION_PROMPT = "<MORE_DETAILED_CAPTION>"


def _florence_dispatch_interval_seconds() -> float:
    cfg = get_models().get("florence", {})
    if isinstance(cfg, dict):
        interval = cfg.get("dispatch_interval_seconds", 0.5)
        try:
            interval = float(interval)
        except (TypeError, ValueError):
            interval = 0.5
        return max(0.2, interval)
    return 0.5


def _florence_max_new_tokens() -> int:
    cfg = get_models().get("florence", {})
    if isinstance(cfg, dict):
        tokens = cfg.get("max_new_tokens", 512)
        try:
            tokens = int(tokens)
        except (TypeError, ValueError):
            tokens = 512
        return max(32, min(512, tokens))
    return 512


def _florence_caption_batch_size() -> int:
    cfg = get_models().get("florence", {})
    if isinstance(cfg, dict):
        batch_size = cfg.get("caption_batch_size", 2)
        try:
            batch_size = int(batch_size)
        except (TypeError, ValueError):
            batch_size = 2
        return max(1, min(16, batch_size))
    return 2


def _strip_caption_tokens(text: str) -> str:
    return (
        text.replace("<MORE_DETAILED_CAPTION>", "")
        .replace("<DETAILED_CAPTION>", "")
        .replace("MORE_DETAILED_CAPTION", "")
        .replace("DETAILED_CAPTION", "")
        .strip()
    )


@dataclass
class FlorenceCameraSlot:
    camera_id: str
    latest_frame: np.ndarray | None = None
    latest_metadata: dict | None = None
    pending: bool = False
    pending_version: int = 0
    pending_at: float = 0.0
    last_captioned_at: float = 0.0
    last_caption: str | None = None
    last_error: str | None = None


class FlorenceRoundRobinScheduler:
    """Fair round-robin Florence dispatcher with one global caption per second."""

    def __init__(self, dispatch_interval_seconds: float = 0.5):
        self.dispatch_interval_seconds = dispatch_interval_seconds
        self._lock = threading.RLock()
        self._wake_event = threading.Event()
        self._thread = None
        self._running = False
        self._captioning = False
        self._captioned_total = 0
        self._rotation_cursor = 0
        self._last_dispatch_monotonic = 0.0
        self._active_camera_id = None
        self._active_camera_ids_batch: list[str] = []
        self._slots: dict[str, FlorenceCameraSlot] = {}

    def ensure_started(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="Florence_RoundRobinScheduler",
            )
            self._thread.start()
            logger.info("[FLORENCE-TRACE] fair round-robin scheduler started")

    def stop(self):
        with self._lock:
            self._running = False
            self._wake_event.set()
            thread = self._thread
        if thread:
            thread.join(timeout=5)

    def register_pending_frame(self, camera_id: str, frame: np.ndarray, metadata: dict) -> bool:
        self.ensure_started()
        now = time.time()
        slot_metadata = dict(metadata or {})
        slot_metadata.setdefault("camera_id", camera_id)
        with self._lock:
            slot = self._slots.get(camera_id)
            if slot is None:
                slot = FlorenceCameraSlot(camera_id=camera_id)
                self._slots[camera_id] = slot
            slot.latest_frame = frame
            slot.latest_metadata = slot_metadata
            slot.pending = True
            slot.pending_version += 1
            slot.pending_at = now
            slot.last_error = None
            pending_count = self._count_pending_locked()
            logger.info(
                f"[FLORENCE-TRACE] corr={slot_metadata.get('corr_id', '?')} cam={camera_id} ENQUEUED "
                f"(pending_cameras={pending_count})"
            )
        self._wake_event.set()
        return True

    def unregister_camera(self, camera_id: str):
        with self._lock:
            self._slots.pop(camera_id, None)
            if self._active_camera_id == camera_id:
                self._active_camera_id = None
            if camera_id in self._active_camera_ids_batch:
                self._active_camera_ids_batch = [cid for cid in self._active_camera_ids_batch if cid != camera_id]
        self._wake_event.set()

    def _count_pending_locked(self) -> int:
        try:
            from ...workers.ai_worker import active_ai_workers
            active_ids = set(active_ai_workers.keys()) if active_ai_workers else set(self._slots.keys())
        except Exception:
            active_ids = set(self._slots.keys())
        return sum(1 for camera_id, slot in self._slots.items() if camera_id in active_ids and slot.pending)

    def _active_camera_ids(self) -> list[str]:
        try:
            from ...workers.ai_worker import active_ai_workers
            active_ids = set(active_ai_workers.keys())
            if not active_ids:
                active_ids = set(self._slots.keys())
            return sorted(active_ids)
        except Exception:
            return sorted(self._slots.keys())

    def _select_next_batch_locked(self, active_ids: list[str], batch_size: int):
        if not active_ids:
            return None

        batch_size = max(1, batch_size)
        camera_count = len(active_ids)
        self._rotation_cursor %= camera_count
        start_index = self._rotation_cursor
        selected = []

        for offset in range(camera_count):
            if len(selected) >= batch_size:
                break
            index = (start_index + offset) % camera_count
            camera_id = active_ids[index]
            slot = self._slots.get(camera_id)
            if slot is None:
                continue
            if not slot.pending or slot.latest_frame is None:
                continue

            slot.pending = False
            selected.append((camera_id, slot, slot.pending_version))
            self._rotation_cursor = (index + 1) % camera_count

        if selected:
            self._captioning = True
            self._active_camera_id = selected[0][0]
            self._active_camera_ids_batch = [camera_id for camera_id, _, _ in selected]
            self._last_dispatch_monotonic = time.monotonic()
            return selected

        return None

    def _scheduler_loop(self):
        while True:
            self._wake_event.wait(timeout=0.1)
            self._wake_event.clear()

            with self._lock:
                if not self._running:
                    break
                if self._captioning:
                    continue

                self.dispatch_interval_seconds = _florence_dispatch_interval_seconds()
                batch_size = _florence_caption_batch_size()

                elapsed = time.monotonic() - self._last_dispatch_monotonic
                if elapsed < self.dispatch_interval_seconds:
                    continue

                active_ids = self._active_camera_ids()
                selection = self._select_next_batch_locked(active_ids, batch_size)
                if selection is None:
                    continue

                batch = selection
                camera_ids = [camera_id for camera_id, _, _ in batch]
                frames = [slot.latest_frame for _, slot, _ in batch]
                metadata_list = [dict(slot.latest_metadata or {}) for _, slot, _ in batch]
                corr_id = metadata_list[0].get("corr_id") if metadata_list else None
                logger.info(
                    f"[FLORENCE-TRACE] corr={corr_id} cam={camera_ids[0] if camera_ids else '?'} frame=dispatch "
                    f"turn granted (active={len(active_ids)}, cursor={self._rotation_cursor}, batch={len(batch)})"
                )

            captions = None
            error_text = None
            try:
                logger.warning(
                    f"[Florence-2 Orchestrator] Invoking async captioner batch for cameras {camera_ids}"
                )
                captions = generate_scene_captions(frames, corr_id=corr_id)
                logger.info(f"[FLORENCE-TRACE] corr={corr_id} batch_size={len(batch)} generate_scene_captions completed")
            except Exception as exc:
                error_text = str(exc)
                logger.exception(f"[FLORENCE-TRACE] corr={corr_id} batch caption generation failed")
            finally:
                with self._lock:
                    self._captioning = False
                    self._active_camera_id = None
                    self._active_camera_ids_batch = []
                    for index, (camera_id, slot, dispatch_version) in enumerate(batch):
                        current_slot = self._slots.get(camera_id)
                        if current_slot is not None:
                            if current_slot.pending_version == dispatch_version:
                                current_slot.pending = False
                            current_slot.last_captioned_at = time.time()
                            caption = captions[index] if captions and index < len(captions) else None
                            if caption:
                                current_slot.last_caption = caption
                                current_slot.last_error = None
                                self._captioned_total += 1
                            elif error_text:
                                current_slot.last_error = error_text
                self._wake_event.set()

            if captions:
                for index, caption in enumerate(captions):
                    if not caption:
                        continue
                    camera_id = batch[index][0] if index < len(batch) else "?"
                    try:
                        metadata = metadata_list[index]
                        metadata_for_persistence = dict(metadata)
                        metadata_for_persistence["frame"] = frames[index] if index < len(frames) else None
                        _persister_executor.submit(_async_caption_persister, caption, metadata_for_persistence)
                    except Exception as persister_exc:
                        logger.warning(f"[FLORENCE-TRACE] corr={corr_id} cam={camera_id} persister submit failed: {persister_exc}")

    def get_stats(self) -> dict:
        with self._lock:
            active_ids = self._active_camera_ids()
            camera_stats = {}
            pending_count = 0
            for camera_id in active_ids:
                slot = self._slots.get(camera_id)
                if slot is None:
                    continue
                is_pending = bool(slot.pending and slot.latest_frame is not None)
                if is_pending:
                    pending_count += 1
                camera_stats[camera_id] = {
                    "pending": is_pending,
                    "pending_since": datetime.datetime.fromtimestamp(slot.pending_at, IST_TZ).isoformat() if slot.pending_at else None,
                    "last_captioned_at": datetime.datetime.fromtimestamp(slot.last_captioned_at, IST_TZ).isoformat() if slot.last_captioned_at else None,
                    "last_caption": slot.last_caption,
                    "last_error": slot.last_error,
                }

            return {
                "captioning": 1 if self._captioning else 0,
                "queue": pending_count,
                "captioned": self._captioned_total,
                "active_cameras": active_ids,
                "camera_stats": camera_stats,
                "rotation_cursor": self._rotation_cursor,
            }


_round_robin_scheduler = FlorenceRoundRobinScheduler()


def pre_warm():
    """
    Pre-load the Florence-2 model in the main thread at application startup.
    This avoids thread-safety issues with transformers' lazy module imports
    when the model is first needed inside a background worker thread.
    """
    cfg = get_models()
    if cfg.get("demo_mode", False):
        return
    try:
        logger.info("Pre-warming Florence-2 model at startup...")
        model_manager.get_florence()
        logger.info("Florence-2 model pre-warm complete.")
    except Exception:
        logger.exception("Florence-2 pre-warm failed.")


def generate_scene_captions(frames: list[np.ndarray], corr_id: str | None = None) -> list[str | None]:
    """
    Direct Florence-2 caption generation for one or more frames.
    Batches frames to improve GPU utilization and reduce per-caption host overhead.
    """
    if not frames:
        return []

    cfg = get_models()
    if cfg.get("demo_mode", False):
        return [random.choice(MOCK_DESCRIPTIONS) for _ in frames]

    try:
        logger.warning(f"[Florence-2 Debug] corr={corr_id} 1. Getting Florence model from ModelManager...")
        t0 = time.time()
        florence_res = model_manager.get_florence()
        logger.warning(f"[Florence-2 Debug] corr={corr_id} get_florence() took {time.time()-t0:.2f}s")
        if florence_res is None or not isinstance(florence_res, tuple):
            logger.warning(f"[Florence-2 Debug] corr={corr_id} Model not available or invalid tuple returned")
            return [None for _ in frames]
        model, processor = florence_res

        logger.warning(f"[Florence-2 Debug] corr={corr_id} 2. Converting {len(frames)} frame(s) to RGB PIL Images...")
        pil_images = []
        for frame in frames:
            if frame is None or frame.size == 0:
                pil_images.append(None)
                continue
            h, w = frame.shape[:2]
            if w > 640 or h > 360:
                proc_frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
            else:
                proc_frame = frame
            rgb_image = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2RGB)
            pil_images.append(Image.fromarray(rgb_image))

        valid_indexes = [index for index, image in enumerate(pil_images) if image is not None]
        if not valid_indexes:
            return [None for _ in frames]

        valid_images = [pil_images[index] for index in valid_indexes]
        logger.warning(f"[Florence-2 Debug] corr={corr_id} 3. Processor encoding prompt and {len(valid_images)} image(s)...")
        inputs = processor(text=[CAPTION_PROMPT] * len(valid_images), images=valid_images, return_tensors="pt", padding=True)

        device = next(model.parameters()).device
        dtype = next(model.parameters()).dtype

        logger.warning(f"[Florence-2 Debug] corr={corr_id} 4. Entering RLock (device={device}, dtype={dtype})...")
        with model_manager._florence_lock:
            input_ids = inputs["input_ids"].to(device)
            pixel_values = inputs["pixel_values"].to(device).to(dtype)

            logger.warning(f"[Florence-2 Debug] corr={corr_id} 5. Calling model.generate on CUDA...")
            t_gen0 = time.time()
            max_new_tokens = _florence_max_new_tokens()
            eos_id = getattr(getattr(processor, "tokenizer", None), "eos_token_id", 2)
            pad_id = getattr(getattr(processor, "tokenizer", None), "pad_token_id", 1)
            gen_kwargs = {
                "input_ids": input_ids,
                "pixel_values": pixel_values,
                "max_new_tokens": max_new_tokens,
                "do_sample": False,
                "num_beams": 1,
                "use_cache": True,
                "eos_token_id": eos_id,
                "pad_token_id": pad_id
            }

            # Run Florence on its dedicated CUDA stream so YOLO's default stream
            # can proceed in parallel. Falls back to default stream on any error.
            generated_ids = _run_florence_on_stream(model, gen_kwargs, corr_id=corr_id)
            logger.warning(f"[Florence-2 Debug] corr={corr_id} model.generate() took {time.time()-t_gen0:.2f}s")
            logger.warning(f"[Florence-2 Debug] corr={corr_id} 6. model.generate completed successfully!")

        decoded_texts = processor.batch_decode(generated_ids, skip_special_tokens=True)
        cleaned_valid = [_strip_caption_tokens(text) for text in decoded_texts]
        captions = [None for _ in frames]
        for index, cleaned in zip(valid_indexes, cleaned_valid):
            captions[index] = cleaned
        logger.warning(f"[Florence-2 Debug] corr={corr_id} 7. Batch captions generated: {[c[:60] if c else None for c in captions]}")
        return captions

    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        logger.warning(f"[Florence-2 Debug] corr={corr_id} CUDA OOM — cache cleared")
        return [None for _ in frames]
    except Exception as exc:
        logger.warning(f"[Florence-2 Debug] corr={corr_id} Generation error: {exc}")
        return [None for _ in frames]


def _run_florence_on_stream(
    model,
    gen_kwargs: dict,
    corr_id: str | None = None,
):
    """
    Run Florence model.generate() on the dedicated CUDA stream.
    Falls back gracefully:
      - OOM on stream      → clear cache, retry on default stream
      - Any other error    → log warning, retry on default stream
      - No dedicated stream (CPU or creation failed) → default stream
    """
    if _florence_cuda_stream is not None:
        try:
            with torch.cuda.stream(_florence_cuda_stream):
                with torch.inference_mode():
                    result = model.generate(**gen_kwargs)
            # Synchronise only the Florence stream — YOLO's default stream is unaffected.
            _florence_cuda_stream.synchronize()
            logger.debug(f"[Florence stream] corr={corr_id} inference completed on dedicated stream.")
            return result
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            logger.warning(
                f"[Florence stream OOM] corr={corr_id} — cache cleared, retrying on default stream."
            )
        except Exception as stream_err:
            logger.warning(
                f"[Florence stream error] corr={corr_id} {stream_err!r} — falling back to default stream."
            )
    # Default stream fallback (handles CPU, stream creation failure, or retry after OOM)
    with torch.inference_mode():
        return model.generate(**gen_kwargs)


def generate_scene_caption(frame: np.ndarray, corr_id: str | None = None) -> str | None:
    captions = generate_scene_captions([frame], corr_id=corr_id)
    return captions[0] if captions else None


def get_florence_queue_stats() -> dict:
    return _round_robin_scheduler.get_stats()


# ---------------------------------------------------------------------------
# YOLO ↔ Florence frame-binding map (strict TTL-based, no count eviction)
#
# Each entry: corr_id → (yolo_summary, inserted_at_monotonic)
# TTL = 3 minutes.  If Florence hasn't processed the frame within 3 minutes the
# YOLO summary is considered stale and the caption is stored Florence-only.
# This prevents any possibility of mismatched YOLO+Florence captions.
# ---------------------------------------------------------------------------
_YOLO_SUMMARY_TTL_SECONDS: float = 180.0  # 3 minutes
yolo_correlation_map: dict[str, tuple[str, float]] = {}
_yolo_lock = threading.Lock()


def record_yolo_frame_summary(corr_id: str, yolo_summary: str) -> None:
    """Stores YOLO summary bound to a frame corr_id for later Florence pairing.

    Strict rule: only stored when both corr_id and summary are non-empty.
    Map is TTL-pruned (3 min) on every write when size exceeds 2 000 entries.
    Never raises — YOLO pipeline must not be disrupted by map errors.
    """
    if not corr_id or not yolo_summary:
        return
    try:
        now = time.monotonic()
        with _yolo_lock:
            yolo_correlation_map[corr_id] = (yolo_summary, now)
            # TTL-prune when map is large (avoids unbounded growth on long-running servers)
            if len(yolo_correlation_map) > 2000:
                cutoff = now - _YOLO_SUMMARY_TTL_SECONDS
                expired_keys = [
                    k for k, (_, ts) in yolo_correlation_map.items() if ts < cutoff
                ]
                for k in expired_keys:
                    yolo_correlation_map.pop(k, None)
        with _round_robin_scheduler._lock:
            for slot in _round_robin_scheduler._slots.values():
                if slot.latest_metadata and slot.latest_metadata.get("corr_id") == corr_id:
                    slot.latest_metadata["yolo_summary"] = yolo_summary
    except Exception:
        pass  # Never crash the YOLO pipeline due to a map bookkeeping error


def get_yolo_frame_summary(corr_id: str) -> str:
    """Retrieves the YOLO summary bound to corr_id, enforcing the 3-minute TTL.

    Returns empty string (Florence-only path) on any failure:
      - corr_id not found (unknown frame)
      - entry expired (> 3 min since YOLO ran)
      - any internal error
    This guarantees YOLO and Florence captions are NEVER spliced from different frames.
    """
    if not corr_id:
        return ""  # No corr_id → always Florence-only
    try:
        now = time.monotonic()
        with _yolo_lock:
            entry = yolo_correlation_map.get(corr_id)
            if entry is None:
                return ""  # Unknown frame → Florence stores alone
            summary, inserted_at = entry
            if (now - inserted_at) > _YOLO_SUMMARY_TTL_SECONDS:
                # Expired: remove and return empty — do not splice stale YOLO data
                yolo_correlation_map.pop(corr_id, None)
                logger.info(
                    f"[YOLO-MAP] corr={corr_id} TTL expired ({_YOLO_SUMMARY_TTL_SECONDS:.0f}s) "
                    "— Florence caption stored without YOLO binding."
                )
                return ""
            return summary
    except Exception:
        return ""  # Any map error → Florence stores alone safely, no mismatch


def _async_caption_persister(florence_cap: str, metadata: dict):
    if not metadata:
        return
    corr_id = metadata.get("corr_id", "?") if metadata else "?"
    camera_id = metadata.get("camera_id", "cam_1")
    frame = metadata.get("frame")

    from backend.ai.captioning.caption_integrity import caption_integrity_validator
    is_valid, reason, envelope = caption_integrity_validator.validate_and_claim(
        image_id=corr_id,
        camera_id=camera_id,
        frame=frame,
        raw_caption=florence_cap
    )

    if not is_valid:
        logger.error(f"[Florence INTEGRITY REJECTED] {reason}")
        return

    logger.info(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER ENTER cam={camera_id}")
    try:
        import os
        import datetime
        from ...database.connection import SessionLocal
        from ...database.models import SceneCaption
        from ..embeddings.embedder import get_text_embedding
        from ...messaging.kafka_client import event_client

        # Retrieve bound YOLO summary for the exact frame correlation ID
        # Strict frame binding: YOLO summary retrieved by exact corr_id match.
        # If expired or not found, caption is stored Florence-only — never spliced.
        yolo_summary = metadata.get("yolo_summary") or get_yolo_frame_summary(corr_id)
        f_text = florence_cap if florence_cap else "Active surveillance scene"

        # Embed frame capture timestamp so the UI can show "captured X ago"
        frame_ts = metadata.get("frame_ts", "")
        ts_suffix = f" | ts={frame_ts}" if frame_ts else ""  # omit if not available (old frames / fallback)

        if yolo_summary:
            full_caption = f"[YOLO]: {yolo_summary} | [Florence-2]: {f_text} | camera {camera_id}{ts_suffix}"
        else:
            full_caption = f"[Florence-2]: {f_text} | camera {camera_id}{ts_suffix}"

        embedding = None
        try:
            embedding = get_text_embedding(full_caption)
        except Exception as e:
            logger.warning(f"[{camera_id}] Async embedding error: {e}")

        vid = corr_id if corr_id else f"img_{uuid.uuid4().hex[:12]}"
        snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "snapshots"))
        os.makedirs(snap_dir, exist_ok=True)
        snap_url = f"/api/v1/playback/snapshot/{vid}"

        if frame is not None:
            snap_path = os.path.join(snap_dir, f"{vid}.jpg")
            try:
                from ...workers.ai_worker import save_snapshot_async
                save_snapshot_async(snap_path, frame, is_critical=True)
            except Exception:
                pass

        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz)

        with SessionLocal() as db:
            db_caption = SceneCaption(
                camera_id=camera_id,
                caption=full_caption,
                snapshot_url=snap_url,
                timestamp=now_ist
            )
            db.add(db_caption)
            db.commit()
            logger.info(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER DB commit OK, "
                        f"scene_caption_id={db_caption.id}")

        if embedding is not None:
            try:
                # BUG-05 FIX: Extract dominant YOLO class from the caption prefix so the
                # Qdrant payload carries a structured yolo_class field for cross-class filtering.
                _yolo_class = None
                if yolo_summary:
                    # yolo_summary is like "1 black motorcycle, 2 person" — grab first noun
                    import re as _re
                    _match = _re.search(r'\b(car|motorcycle|truck|bus|bicycle|person|van|suv|rickshaw|scooter|moped)\b', yolo_summary.lower())
                    if _match:
                        _yolo_class = _match.group(1)

                from ...workers.ai_worker import index_vector
                index_vector(
                    vector_id=vid,
                    vector=embedding,
                    payload={
                        "type": "scene",
                        "camera_id": camera_id,
                        "caption": full_caption,
                        "snapshot_url": snap_url,
                        "timestamp": now_ist.isoformat(),
                        "yolo_class": _yolo_class,
                    }
                )
                logger.info(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER vector indexed "
                            f"vid={vid}")
            except Exception as idx_err:
                logger.warning(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER vector indexing failed: {idx_err}")
                logger.warning(f"[{camera_id}] Async vector index error: {idx_err}")

        try:
            event_client.publish_event("captions", {
                "camera_id": camera_id,
                "caption": full_caption,
                "timestamp": now_ist.isoformat()
            })
            logger.info(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER COMPLETE, "
                        f"kafka event published")
        except Exception as k_err:
            logger.warning(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER Kafka event publish warning: {k_err}")
        logger.warning(f"[Florence-2 Async] Enriched caption persisted for camera {camera_id}: {f_text[:80]}...")

    except Exception as exc:
        logger.warning(f"[Florence-2 Async] Persistence error: {exc}")


def submit_async_scene_caption(
    frame: np.ndarray,
    camera_id: str,
    yolo_summary: str = "",
    corr_id: str | None = None,
    frame_ts: str = "",
) -> bool:
    """Submit a frame to the async Florence caption queue.

    Args:
        frame:        Raw BGR numpy frame from the camera.
        camera_id:    Camera identifier string.
        yolo_summary: YOLO detection summary for this exact frame (bound by corr_id).
        corr_id:      Unique correlation ID for this frame (used for strict YOLO binding).
        frame_ts:     IST wall-clock timestamp string of when the frame was captured
                      (embedded in the stored caption as ``ts=...`` for UI staleness display).
    """
    from backend.ai.captioning.caption_integrity import caption_integrity_validator
    image_id, envelope = caption_integrity_validator.create_envelope(
        frame=frame,
        camera_id=camera_id,
        yolo_summary=yolo_summary,
        custom_id=corr_id
    )

    logger.info(f"[FLORENCE-TRACE] image_id={image_id} cam={camera_id} "
                f"ENTER submit_async_scene_caption frame_shape="
                f"{None if frame is None else frame.shape}")
    logger.warning(f"[Florence-2 Submitter] Submitting frame to async queue for camera {camera_id}")
    metadata = {
        "camera_id": camera_id,
        "yolo_summary": yolo_summary,
        "corr_id": image_id,
        "frame_ts": frame_ts,   # wall-clock capture time — embedded in stored caption
        "frame": frame.copy() if frame is not None else None
    }
    return _round_robin_scheduler.register_pending_frame(camera_id, frame, metadata)


def unregister_florence_camera(camera_id: str):
    _round_robin_scheduler.unregister_camera(camera_id)