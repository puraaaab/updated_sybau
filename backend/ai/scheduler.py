import queue
import threading
import time
import uuid


class InferenceScheduler:
    """
    Single-threaded priority queue scheduler for GPU inference tasks.

    Only one model runs at a time (prevents VRAM contention between YOLO and
    Florence-2). Tasks block the calling thread until the scheduler processes
    them, so callers get results synchronously.

    Priority values (lower integer = higher priority):
        PRIORITY_YOLO        = 1  — every sampled frame, must be fastest
        PRIORITY_VEHICLE_OCR = 2  — only when vehicle detected
        PRIORITY_FACE_REID   = 3  — only when person detected
        PRIORITY_FLORENCE    = 4  — every N frames, heaviest model
    """

    PRIORITY_YOLO = 1
    PRIORITY_VEHICLE_OCR = 2
    PRIORITY_FACE_REID = 3
    PRIORITY_FLORENCE = 4

    # Timeout (seconds) for a scheduled task to complete before raising.
    # Florence-2 can take up to 30s to run on large frames, so we give plenty of margin.
    TASK_TIMEOUT_SECONDS = 60.0

    def __init__(self):
        self.request_queue = queue.PriorityQueue()
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
        print("[InferenceScheduler] Priority Queue thread active.")

    def stop(self):
        with self._lifecycle_lock:
            if not self.running:
                return
            self.running = False
            # Wake up the scheduler loop if it is blocked on queue.get()
            # by inserting a sentinel task
            sentinel = (0, 0.0, "STOP", None, (), {}, None, None)
            self.request_queue.put(sentinel)
            worker = self.worker_thread
        if worker:
            worker.join(timeout=5)

    def schedule_inference(self, priority: int, inference_func, *args, **kwargs):
        """
        Submit an inference task to the queue and block until it completes.
        Raises the underlying exception if the task fails.
        Raises TimeoutError if the task does not finish within TASK_TIMEOUT_SECONDS.
        """
        if not self.running or not (self.worker_thread and self.worker_thread.is_alive()):
            self.start()

        task_id = str(uuid.uuid4())
        result_container = {"result": None, "exception": None}
        done_event = threading.Event()

        # Tuple order: (priority, timestamp, task_id, func, args, kwargs, result, event)
        # timestamp used as FIFO tie-breaker for same-priority tasks
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

        # Block the calling thread until the scheduler processes the task,
        # with a timeout to prevent infinite blocking on shutdown
        completed = done_event.wait(timeout=self.TASK_TIMEOUT_SECONDS)
        if not completed:
            raise TimeoutError(
                f"[InferenceScheduler] Task {task_id[:8]} timed out after "
                f"{self.TASK_TIMEOUT_SECONDS}s (priority={priority})"
            )

        if result_container["exception"]:
            raise result_container["exception"]
        return result_container["result"]

    def _scheduler_loop(self):
        while self.running or not self.request_queue.empty():
            try:
                try:
                    task = self.request_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                priority, timestamp, task_id, func, args, kwargs, result_container, done_event = task

                # Sentinel: scheduler is stopping
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

            except Exception as e:
                print(f"[InferenceScheduler] Unexpected loop error: {e}")

        print("[InferenceScheduler] Worker thread stopped.")


# Global scheduler instance
inference_scheduler = InferenceScheduler()
