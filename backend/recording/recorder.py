import os
import cv2
import time
import datetime
import threading
from ..config.service import get_cameras
from ..services.stream_manager import stream_manager

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))

class CameraRecorder:
    """
    Per-camera continuous recording worker using unified StreamManager.
    
    Production behaviour:
    • Pulls live video frames from the shared camera StreamManager
    • Records video frames into 30-second MP4 segments
    • Reconnects/waits gracefully if camera stream is reconnecting
    """

    def __init__(self, camera_id: str, stream_url: str):
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.running = False
        self.thread = None
        self.segment_duration = 30.0 # 30-second clips
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._recording_loop, daemon=True)
        self.thread.start()
        print(f"Recording worker started for Camera {self.camera_id}")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        stream_manager.release_stream(self.camera_id)
            
    def _recording_loop(self):
        os.makedirs(os.path.join(STORAGE_DIR, self.camera_id), exist_ok=True)
        stream = stream_manager.get_stream(self.camera_id, self.stream_url)

        try:
            while self.running:
                # Wait until stream is online and supplying frames
                if not stream.is_online:
                    time.sleep(0.5)
                    continue

                width, height = stream.frame_shape
                record_fps = stream.fps if stream.fps and stream.fps > 0 else 10.0

                # ── Segment recording loop ───────────────────────────────────
                now = datetime.datetime.now()
                timestamp_str = now.strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp_str}.mp4"
                filepath = os.path.join(STORAGE_DIR, self.camera_id, filename)

                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(filepath, fourcc, record_fps, (width, height))

                try:
                    segment_start = time.time()
                    frames_written = 0
                    last_frame_ts = 0.0

                    while self.running and (time.time() - segment_start) < self.segment_duration:
                        success, frame, ts = stream.get_frame(last_frame_ts)
                        if not success or frame is None:
                            time.sleep(1.0 / record_fps)
                            continue

                        last_frame_ts = ts
                        out.write(frame)
                        frames_written += 1
                        time.sleep(1.0 / record_fps)
                finally:
                    out.release()

                # Delete empty segment files
                if frames_written == 0:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
        finally:
            stream_manager.release_stream(self.camera_id)

# Global dictionary to track active recorders
active_recorders = {}

from ..database.connection import SessionLocal
from ..database.models import Camera

def start_all_recorders():
    db = SessionLocal()
    try:
        cameras = db.query(Camera).all()
        for cam in cameras:
            cid = cam.id
            if cid not in active_recorders:
                recorder = CameraRecorder(cid, cam.stream_url)
                active_recorders[cid] = recorder
                recorder.start()
    finally:
        db.close()

def stop_all_recorders():
    for cid, recorder in list(active_recorders.items()):
        recorder.stop()
        del active_recorders[cid]
