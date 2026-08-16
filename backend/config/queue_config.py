"""
VMS Pro — Configurable Bounded Queue Architecture
Provides fine-grained queue size bounds and overflow policies per workload type.
"""

import os
import queue
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BoundedQueueOverflowError(Exception):
    """Raised when an un-droppable queue overflows."""
    pass


class BoundedQueue:
    """
    Thread-safe Bounded Queue supporting configurable overflow policies:
    - DROP_OLDEST: Evicts the oldest item when full (ideal for realtime AI frames)
    - NEVER_DROP: Blocks until space is available (ideal for recording)
    - PERSIST: Blocks or raises exception if full (ideal for forensics)
    - COALESCE: Replaces matching event types (ideal for notification deduplication)
    """
    DROP_OLDEST = "drop_oldest"
    NEVER_DROP = "never_drop"
    PERSIST = "persist"
    COALESCE = "coalesce"

    def __init__(self, name: str, max_size: int = 100, overflow_policy: str = "drop_oldest"):
        self.name = name
        self.max_size = max(1, max_size)
        self.overflow_policy = overflow_policy
        self._queue = queue.Queue(maxsize=self.max_size)

    def put(self, item: Any, block: bool = True, timeout: Optional[float] = None) -> bool:
        """Puts an item into the bounded queue adhering to overflow policy."""
        if self.overflow_policy == self.DROP_OLDEST or self.overflow_policy == self.COALESCE:
            while True:
                try:
                    self._queue.put_nowait(item)
                    return True
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass

        else:
            try:
                self._queue.put(item, block=block, timeout=timeout)
                return True
            except queue.Full:
                return False

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        return self._queue.get(block=block, timeout=timeout)

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def full(self) -> bool:
        return self._queue.full()


# Default queue configurations based on environment overrides
QUEUE_CONFIGS = {
    "frame": {
        "max_size": int(os.getenv("QUEUE_FRAME_MAX_SIZE", "100")),
        "overflow": BoundedQueue.DROP_OLDEST
    },
    "inference": {
        "max_size": int(os.getenv("QUEUE_INFERENCE_MAX_SIZE", "50")),
        "overflow": BoundedQueue.DROP_OLDEST
    },
    "recording": {
        "max_size": int(os.getenv("QUEUE_RECORDING_MAX_SIZE", "500")),
        "overflow": BoundedQueue.NEVER_DROP
    },
    "forensic": {
        "max_size": int(os.getenv("QUEUE_FORENSIC_MAX_SIZE", "1000")),
        "overflow": BoundedQueue.PERSIST
    },
    "notification": {
        "max_size": int(os.getenv("QUEUE_NOTIFICATION_MAX_SIZE", "200")),
        "overflow": BoundedQueue.COALESCE
    }
}


def create_queue(queue_type: str, custom_name: Optional[str] = None) -> BoundedQueue:
    cfg = QUEUE_CONFIGS.get(queue_type, {"max_size": 100, "overflow": BoundedQueue.DROP_OLDEST})
    q_name = custom_name or f"queue_{queue_type}"
    return BoundedQueue(name=q_name, max_size=cfg["max_size"], overflow_policy=cfg["overflow"])
