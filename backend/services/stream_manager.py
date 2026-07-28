import time
import cv2
import threading
import numpy as np
import logging
from typing import Optional, Tuple
from .stream_resolver import resolve_stream_url, invalidate_cache
from ..monitoring.camera_state import CameraStateMachine

logger = logging.getLogger(__name__)

class CameraStream:
    """
    Manages a single background VideoCapture thread for a camera stream.
    Shares the latest frame between Recorder, AI Worker, and Telemetry.
    """
    MAX_RECONNECT_WAIT = 60

    def __init__(self, camera_id: str, stream_url: str):
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_frame_time: float = 0.0
        self.frame_shape: Tuple[int, int] = (640, 480)
        self.fps: float = 10.0
        self.is_online = False
        self.ref_count = 0

    def add_consumer(self):
        with self._lock:
            self.ref_count += 1
            if not self.running:
                self.start()

    def remove_consumer(self):
        with self._lock:
            self.ref_count = max(0, self.ref_count - 1)
            if self.ref_count == 0 and self.running:
                self.stop()

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info(f"[StreamManager] Capture thread started for Camera {self.camera_id}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None
        CameraStateMachine.update_state(self.camera_id, CameraStateMachine.DISCONNECTED)
        logger.info(f"[StreamManager] Capture thread stopped for Camera {self.camera_id}")

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Returns (success, frame_copy, timestamp).
        """
        with self._lock:
            if self.latest_frame is None:
                return False, None, 0.0
            return True, self.latest_frame.copy(), self.latest_frame_time

    def get_latest_frame(self) -> Tuple[Optional[np.ndarray], float]:
        """
        Returns (frame_copy, timestamp) for DeadlinedBatchCollector compatibility.
        """
        with self._lock:
            if self.latest_frame is None:
                return None, 0.0
            return self.latest_frame.copy(), self.latest_frame_time

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        CameraStateMachine.update_state(self.camera_id, CameraStateMachine.CONNECTING)
        resolved_url = resolve_stream_url(self.camera_id, self.stream_url)
        if not resolved_url:
            CameraStateMachine.update_state(self.camera_id, CameraStateMachine.FAILED)
            return None

        cap = cv2.VideoCapture(resolved_url)
        if cap.isOpened():
            CameraStateMachine.update_state(self.camera_id, CameraStateMachine.ONLINE)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            stream_fps = cap.get(cv2.CAP_PROP_FPS)
            with self._lock:
                self.frame_shape = (w, h)
                self.fps = stream_fps if stream_fps and stream_fps > 0 else 10.0
                self.is_online = True
            print(f"[StreamManager] Camera {self.camera_id} stream opened successfully ({w}x{h} @ {self.fps} FPS)")
            return cap

        cap.release()
        CameraStateMachine.update_state(self.camera_id, CameraStateMachine.FAILED)
        return None

    def _capture_loop(self):
        reconnect_wait = 2

        while self.running:
            cap = self._open_capture()
            if cap is None:
                CameraStateMachine.update_state(self.camera_id, CameraStateMachine.RECONNECTING)
                for _ in range(int(reconnect_wait * 10)):
                    if not self.running:
                        return
                    time.sleep(0.1)
                reconnect_wait = min(reconnect_wait * 2, self.MAX_RECONNECT_WAIT)
                invalidate_cache(self.camera_id)
                continue

            reconnect_wait = 2
            consecutive_failures = 0
            MAX_CONSECUTIVE_FAILURES = 50

            is_file_capture = not (self.stream_url.startswith("rtsp://") or self.stream_url.startswith("http://") or self.stream_url.startswith("https://"))
            frame_interval = 1.0 / max(1.0, self.fps)

            while self.running:
                loop_start = time.time()
                ret, frame = cap.read()
                if not ret or frame is None:
                    # If reading from a local video clip file, loop back to frame 0
                    try:
                        if cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, frame = cap.read()
                    except Exception:
                        pass
                
                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(f"[StreamManager] Camera {self.camera_id} — stream lost, reconnecting")
                        break
                    time.sleep(0.02)
                    continue

                consecutive_failures = 0
                now = time.time()

                with self._lock:
                    self.latest_frame = frame
                    self.latest_frame_time = now

                # Pace local file reading to real-time stream playback speed (1/fps)
                if is_file_capture:
                    elapsed = time.time() - loop_start
                    if elapsed < frame_interval:
                        time.sleep(frame_interval - elapsed)

            if cap and cap.isOpened():
                cap.release()
            invalidate_cache(self.camera_id)

            with self._lock:
                self.is_online = False

            if self.running:
                CameraStateMachine.update_state(self.camera_id, CameraStateMachine.RECONNECTING)
                time.sleep(reconnect_wait)
                reconnect_wait = min(reconnect_wait * 2, self.MAX_RECONNECT_WAIT)


class StreamManager:
    def __init__(self):
        self._streams = {}
        self._lock = threading.Lock()

    def get_stream(self, camera_id: str, stream_url: str = "") -> Optional[CameraStream]:
        with self._lock:
            if camera_id not in self._streams:
                if not stream_url:
                    return None
                self._streams[camera_id] = CameraStream(camera_id, stream_url)
            stream = self._streams[camera_id]
            if stream_url:
                stream.add_consumer()
            return stream

    def release_stream(self, camera_id: str):
        with self._lock:
            if camera_id in self._streams:
                stream = self._streams[camera_id]
                stream.remove_consumer()

    def stop_all(self):
        with self._lock:
            for stream in self._streams.values():
                stream.stop()
            self._streams.clear()

stream_manager = StreamManager()
