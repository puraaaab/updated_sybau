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
            
    def _raise_recording_error(self, error_detail: str):
        """Logs error, updates CameraHealthLog, creates CanonicalEvent, and publishes alert (REL-01)."""
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[CameraRecorder:{self.camera_id}] CAMERA_RECORDING_ERROR: {error_detail}")
        
        db = SessionLocal()
        try:
            from ..database.models import CameraHealthLog, CanonicalEvent, _istnow
            now_dt = _istnow()
            # 1. Update/Add CameraHealthLog
            health_log = CameraHealthLog(
                camera_id=self.camera_id,
                timestamp=now_dt,
                status="CAMERA_RECORDING_ERROR",
                fps=0.0
            )
            db.add(health_log)
            
            # 2. Raise CanonicalEvent alert
            dedup_key = f"{self.camera_id}_CAMERA_RECORDING_ERROR_{int(now_dt.timestamp() // 30)}"
            evt = CanonicalEvent(
                event_uuid=f"ERR_REC_{self.camera_id}_{int(now_dt.timestamp())}",
                deduplication_key=dedup_key,
                camera_id=self.camera_id,
                event_type="CAMERA_RECORDING_ERROR",
                source_type="health",
                source_component="recorder",
                status="DETECTED",
                severity="critical",
                confidence=1.0,
                message=f"Recording/disk failure on Camera {self.camera_id}: {error_detail}",
                timestamp_start=now_dt,
                timestamp_end=now_dt
            )
            db.add(evt)
            db.commit()
            
            # 3. Publish to Kafka/EventBus
            try:
                from ..messaging.kafka_client import event_client
                from ..utils.timezone import format_ist_str
                event_client.publish_event("alerts", {
                    "camera_id": self.camera_id,
                    "type": "CAMERA_RECORDING_ERROR",
                    "severity": "critical",
                    "message": f"Recording/disk failure: {error_detail}",
                    "timestamp": format_ist_str(now_dt),
                })
            except Exception as pe:
                logger.debug(f"[CameraRecorder] Event publish note: {pe}")
        except Exception as e:
            logger.error(f"[CameraRecorder:{self.camera_id}] Error logging health failure: {e}")
            db.rollback()
        finally:
            db.close()

    def _recording_loop(self):
        try:
            os.makedirs(os.path.join(STORAGE_DIR, self.camera_id), exist_ok=True)
        except Exception as e:
            self._raise_recording_error(f"Failed to create storage directory: {e}")

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

                try:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    out = cv2.VideoWriter(filepath, fourcc, record_fps, (width, height))
                    if not out.isOpened():
                        self._raise_recording_error(f"cv2.VideoWriter failed to open {filepath}")
                except Exception as e:
                    self._raise_recording_error(f"VideoWriter initialization failed: {e}")
                    out = None

                frames_written = 0
                if out and out.isOpened():
                    try:
                        segment_start = time.time()
                        last_frame_ts = 0.0

                        while self.running and (time.time() - segment_start) < self.segment_duration:
                            success, frame, ts = stream.get_frame(last_frame_ts)
                            if not success or frame is None:
                                time.sleep(1.0 / record_fps)
                                continue

                            last_frame_ts = ts
                            try:
                                out.write(frame)
                                frames_written += 1
                            except Exception as write_err:
                                self._raise_recording_error(f"Failed writing frame to disk: {write_err}")
                                break
                            time.sleep(1.0 / record_fps)
                    except Exception as loop_err:
                        self._raise_recording_error(f"Recording loop error: {loop_err}")
                    finally:
                        out.release()

                # Delete empty segment files or launch background web-H264 conversion
                if frames_written == 0:
                    try:
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    except OSError:
                        pass
                else:
                    def _convert_to_h264(src_path, cam_id, f_name):
                        try:
                            import subprocess
                            c_dir = os.path.abspath(os.path.join(STORAGE_DIR, "..", "h264_cache", cam_id))
                            os.makedirs(c_dir, exist_ok=True)
                            out_h264 = os.path.join(c_dir, f"h264_{f_name}")
                            res = subprocess.run([
                                "ffmpeg", "-y", "-i", src_path,
                                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                                "-movflags", "+faststart", out_h264
                            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                            if res.returncode != 0:
                                self._raise_recording_error(f"FFmpeg conversion failed: {res.stderr[:200] if res.stderr else 'code ' + str(res.returncode)}")
                        except Exception as conv_err:
                            self._raise_recording_error(f"FFmpeg invocation error: {conv_err}")
                    threading.Thread(target=_convert_to_h264, args=(filepath, self.camera_id, filename), daemon=True).start()
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
