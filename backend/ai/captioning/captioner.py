import logging
import random
import queue
import time
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

CAPTION_PROMPT = (
    "<MORE_DETAILED_CAPTION> "
    "Describe the scene in a single rich paragraph with as much visual detail as possible. "
    "Include people, clothing, actions, vehicles, object positions, colors, lighting, motion, "
    "camera perspective, and background context."
)


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
        tokens = cfg.get("max_new_tokens", 192)
        try:
            tokens = int(tokens)
        except (TypeError, ValueError):
            tokens = 192
        return max(32, tokens)
    return 192


def _florence_caption_batch_size() -> int:
    cfg = get_models().get("florence", {})
    if isinstance(cfg, dict):
        batch_size = cfg.get("caption_batch_size", 2)
        try:
            batch_size = int(batch_size)
        except (TypeError, ValueError):
            batch_size = 2
        return max(1, min(4, batch_size))
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
            active_ids = set(active_ai_workers.keys())
        except Exception:
            active_ids = set(self._slots.keys())
        return sum(1 for camera_id, slot in self._slots.items() if camera_id in active_ids and slot.pending)

    def _active_camera_ids(self) -> list[str]:
        try:
            from ...workers.ai_worker import active_ai_workers
            return sorted(active_ai_workers.keys())
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
                    "pending_since": datetime.datetime.fromtimestamp(slot.pending_at, datetime.timezone.utc).isoformat() if slot.pending_at else None,
                    "last_captioned_at": datetime.datetime.fromtimestamp(slot.last_captioned_at, datetime.timezone.utc).isoformat() if slot.last_captioned_at else None,
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

        logger.warning(f"[Florence-2 Debug] corr={corr_id} 2. Preprocessing {len(frames)} frame(s) (fast 320px scale)...")
        pil_images = []
        for frame in frames:
            if frame is None or frame.size == 0:
                pil_images.append(None)
                continue
            h, w = frame.shape[:2]
            if max(h, w) > 320:
                scale = 320.0 / max(h, w)
                frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_LINEAR)

            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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

            if hasattr(model, "generation_config"):
                model.generation_config.early_stopping = False
                model.generation_config.num_beams = 1

            logger.warning(f"[Florence-2 Debug] corr={corr_id} 5. Calling model.generate on CUDA...")
            t_gen0 = time.time()
            max_new_tokens = _florence_max_new_tokens()
            with torch.inference_mode():
                generated_ids = model.generate(
                    input_ids=input_ids,
                    pixel_values=pixel_values,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    num_beams=1,
                    use_cache=True,
                )
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


def generate_scene_caption(frame: np.ndarray, corr_id: str | None = None) -> str | None:
    captions = generate_scene_captions([frame], corr_id=corr_id)
    return captions[0] if captions else None


def get_florence_queue_stats() -> dict:
    stats = _round_robin_scheduler.get_stats()
    logger.debug(f"[FLORENCE-TRACE] stats poll: {stats}")
    return stats


def _async_caption_persister(florence_cap: str, metadata: dict):
    if not metadata:
        return
    corr_id = metadata.get("corr_id", "?") if metadata else "?"
    camera_id = metadata.get("camera_id", "cam_1")
    logger.info(f"[FLORENCE-TRACE] corr={corr_id} PERSISTER ENTER "
                f"cam={camera_id} caption={'<empty>' if not florence_cap else florence_cap[:60]!r}")
    try:
        import uuid
        import os
        import datetime
        from ...database.connection import SessionLocal
        from ...database.models import SceneCaption
        from ..embeddings.embedder import get_text_embedding
        from ...messaging.kafka_client import event_client

        yolo_summary = metadata.get("yolo_summary", "")
        f_text = florence_cap if florence_cap else "Active surveillance scene"
        
        if yolo_summary:
            full_caption = f"[YOLO]: {yolo_summary} | [Florence-2]: {f_text} | camera {camera_id}"
        else:
            full_caption = f"[Florence-2]: {f_text} | camera {camera_id}"

        embedding = None
        try:
            embedding = get_text_embedding(full_caption)
        except Exception as e:
            logger.warning(f"[{camera_id}] Async embedding error: {e}")

        vid = str(uuid.uuid4())
        snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
        os.makedirs(snap_dir, exist_ok=True)
        snap_url = f"/api/v1/playback/snapshot/{vid}"

        frame = metadata.get("frame")
        if frame is not None:
            snap_path = os.path.join(snap_dir, f"{vid}.jpg")
            try:
                from ...workers.ai_worker import save_snapshot_async
                save_snapshot_async(snap_path, frame)
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
                from ...workers.ai_worker import index_vector
                index_vector(
                    vector_id=vid,
                    vector=embedding,
                    payload={
                        "type": "scene",
                        "camera_id": camera_id,
                        "caption": full_caption,
                        "snapshot_url": snap_url,
                        "timestamp": now_ist.isoformat()
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


def submit_async_scene_caption(frame: np.ndarray, camera_id: str, yolo_summary: str = "", corr_id: str | None = None) -> bool:
    if corr_id is None:
        import uuid
        corr_id = uuid.uuid4().hex[:8]
    logger.info(f"[FLORENCE-TRACE] corr={corr_id} cam={camera_id} "
                f"ENTER submit_async_scene_caption frame_shape="
                f"{None if frame is None else frame.shape}")
    logger.warning(f"[Florence-2 Submitter] Submitting frame to async queue for camera {camera_id}")
    metadata = {
        "camera_id": camera_id,
        "yolo_summary": yolo_summary,
        "corr_id": corr_id
    }
    return _round_robin_scheduler.register_pending_frame(camera_id, frame, metadata)


def unregister_florence_camera(camera_id: str):
    _round_robin_scheduler.unregister_camera(camera_id)