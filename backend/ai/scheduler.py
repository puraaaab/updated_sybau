import queue
import threading
import time
import uuid
import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class InferenceScheduler:
    """
    Production-grade single-GPU batching scheduler for YOLO object tracking and priority tasks.
    Aggregates concurrent per-camera frame requests into dynamic GPU micro-batches (batch size 4-8)
    within a 20ms micro-window to eliminate CUDA thread lock contention across camera worker threads.
    """

    PRIORITY_YOLO = 1
    PRIORITY_VEHICLE_OCR = 2
    PRIORITY_FACE_REID = 3
    PRIORITY_FLORENCE = 4

    TASK_TIMEOUT_SECONDS = 60.0
    MAX_YOLO_BATCH_SIZE = 8
    MAX_BATCH_ACCUMULATION_WAIT_SECONDS = 0.015

    def __init__(self):
        self.request_queue = queue.PriorityQueue()
        self._yolo_queue = queue.Queue()
        self.running = False
        self.worker_thread = None
        self._lifecycle_lock = threading.Lock()

    def start(self):
        with self._lifecycle_lock:
            if self.running and self.worker_thread and self.worker_thread.is_alive():
                return
            self.running = True
            self.worker_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="InferenceScheduler",
            )
            self.worker_thread.start()
        print("[InferenceScheduler] Dynamic Batching Priority Queue thread active.")

    def stop(self):
        with self._lifecycle_lock:
            if not self.running:
                return
            self.running = False
            sentinel = (0, 0.0, "STOP", None, (), {}, None, None)
            self.request_queue.put(sentinel)
            self._yolo_queue.put(None)
            worker = self.worker_thread
        if worker:
            worker.join(timeout=5)

    def schedule_yolo_detection(
        self, camera_id: str, frame: np.ndarray, frame_idx: int
    ) -> List[Dict[str, Any]]:
        """
        Submits a single camera frame to the dynamic YOLO batching queue and blocks
        synchronously until the GPU batch worker returns detection results.
        """
        if not self.running or not (self.worker_thread and self.worker_thread.is_alive()):
            self.start()

        done_event = threading.Event()
        result_holder = {"detections": [], "exception": None}

        task = {
            "camera_id": camera_id,
            "frame": frame,
            "frame_idx": frame_idx,
            "done_event": done_event,
            "result_holder": result_holder,
        }
        self._yolo_queue.put(task)

        completed = done_event.wait(timeout=self.TASK_TIMEOUT_SECONDS)
        if not completed:
            raise TimeoutError(
                f"[InferenceScheduler] YOLO frame task timed out after {self.TASK_TIMEOUT_SECONDS}s for {camera_id}"
            )

        if result_holder["exception"]:
            raise result_holder["exception"]
        return result_holder["detections"]

    def schedule_inference(self, priority: int, inference_func, *args, **kwargs):
        """
        Submit a custom non-batched inference task to the queue and block until completion.
        """
        if not self.running or not (self.worker_thread and self.worker_thread.is_alive()):
            self.start()

        task_id = str(uuid.uuid4())
        result_container = {"result": None, "exception": None}
        done_event = threading.Event()

        task = (
            priority,
            time.monotonic(),
            task_id,
            inference_func,
            args,
            kwargs,
            result_container,
            done_event,
        )
        self.request_queue.put(task)

        completed = done_event.wait(timeout=self.TASK_TIMEOUT_SECONDS)
        if not completed:
            raise TimeoutError(
                f"[InferenceScheduler] Task {task_id[:8]} timed out after "
                f"{self.TASK_TIMEOUT_SECONDS}s (priority={priority})"
            )

        if result_container["exception"]:
            raise result_container["exception"]
        return result_container["result"]

    def _process_yolo_batch(self, initial_req):
        from .detection.yolo import detect_and_track_batch, detect_and_track

        batch_requests = [initial_req]
        deadline = time.monotonic() + self.MAX_BATCH_ACCUMULATION_WAIT_SECONDS

        while len(batch_requests) < self.MAX_YOLO_BATCH_SIZE:
            time_remaining = deadline - time.monotonic()
            if time_remaining <= 0:
                break
            try:
                next_req = self._yolo_queue.get(timeout=max(0.001, time_remaining))
                if next_req is None:
                    break
                batch_requests.append(next_req)
            except queue.Empty:
                break

        frames = [r["frame"] for r in batch_requests]
        stream_ids = [r["camera_id"] for r in batch_requests]
        frame_counters = [r["frame_idx"] for r in batch_requests]

        try:
            if len(batch_requests) == 1:
                det_list = detect_and_track(frames[0])
                batch_results = {stream_ids[0]: det_list}
            else:
                batch_results = detect_and_track_batch(
                    frames, stream_ids, frame_counters, skip_interval=1
                )
            for req in batch_requests:
                cam = req["camera_id"]
                req["result_holder"]["detections"] = batch_results.get(cam, [])
        except Exception as exc:
            logger.warning(f"[InferenceScheduler] YOLO batch processing exception: {exc}")
            for req in batch_requests:
                req["result_holder"]["exception"] = exc
        finally:
            for req in batch_requests:
                req["done_event"].set()

    def _scheduler_loop(self):
        while self.running or not self._yolo_queue.empty() or not self.request_queue.empty():
            try:
                # 1. First priority: Drain pending YOLO batch queue
                try:
                    yolo_req = self._yolo_queue.get_nowait()
                    if yolo_req is not None:
                        self._process_yolo_batch(yolo_req)
                        continue
                except queue.Empty:
                    pass

                # 2. Second priority: Standard priority queue tasks
                try:
                    task = self.request_queue.get(timeout=0.01)
                    priority, timestamp, task_id, func, args, kwargs, result_container, done_event = task
                    if func is None:
                        break
                    try:
                        res = func(*args, **kwargs)
                        result_container["result"] = res
                    except Exception as e:
                        result_container["exception"] = e
                    finally:
                        done_event.set()
                        self.request_queue.task_done()
                except queue.Empty:
                    pass

            except Exception as e:
                print(f"[InferenceScheduler] Unexpected loop error: {e}")

        print("[InferenceScheduler] Worker thread stopped.")


# Global scheduler instance
inference_scheduler = InferenceScheduler()

