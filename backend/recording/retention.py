import os
import time
import datetime
import threading
from sqlalchemy.orm import Session
from ..database.connection import SessionLocal
from ..database.models import Alert

# Path to recordings
STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))

class RetentionManager:
    def __init__(self, retention_days: int = 30, max_disk_usage_percent: float = 85.0):
        self.retention_days = retention_days
        self.max_disk_usage_percent = max_disk_usage_percent
        self.running = False
        self.thread = None
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._retention_loop, daemon=True)
        self.thread.start()
        print("Continuous Video Retention Manager started.")
        
    def stop(self):
        self.running = False
        
    def _retention_loop(self):
        while self.running:
            try:
                self.prune_old_recordings()
            except Exception as e:
                print(f"[RetentionManager] Error during pruning cycle: {e}")
                
            # Sleep 1 hour between checks (or exit immediately if stopped)
            for _ in range(3600):
                if not self.running:
                    break
                time.sleep(1)

    def prune_old_recordings(self):
        if not os.path.exists(STORAGE_DIR):
            return

        db: Session = SessionLocal()
        try:
            # Query all alerts to find protected video files
            alerts = db.query(Alert).all()
            protected_filenames = set()
            for alert in alerts:
                if alert.video_url:
                    # Extract the filename from the URL, e.g., /api/v1/playback/video/cam_01/20260717_153022.mp4
                    parts = alert.video_url.split("/")
                    if len(parts) > 0:
                        protected_filenames.add(parts[-1])

            now = datetime.datetime.now()
            cutoff = now - datetime.timedelta(days=self.retention_days)
            print(f"[RetentionManager] Running pruning cycle. Cutoff: {cutoff.strftime('%Y-%m-%d %H:%M:%S')}")

            # Walk through camera directories
            unprotected_files = []
            
            for camera_id in os.listdir(STORAGE_DIR):
                cam_dir = os.path.join(STORAGE_DIR, camera_id)
                if not os.path.isdir(cam_dir):
                    continue

                for filename in os.listdir(cam_dir):
                    if not filename.endswith(".mp4"):
                        continue

                    # If filename is protected by alert evidence, DO NOT delete!
                    if filename in protected_filenames:
                        continue

                    filepath = os.path.join(cam_dir, filename)
                    # Check modification time
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                    
                    if mtime < cutoff:
                        try:
                            os.remove(filepath)
                            print(f"[RetentionManager] Deleted expired recording: {camera_id}/{filename} (mtime: {mtime.strftime('%Y-%m-%d')})")
                        except OSError as e:
                            print(f"[RetentionManager] Error deleting expired file {filepath}: {e}")
                    else:
                        unprotected_files.append({
                            "filepath": filepath,
                            "mtime": mtime,
                            "camera_id": camera_id,
                            "filename": filename
                        })
            
            # Check physical disk capacity to prevent storage exhaustion
            import shutil
            total, used, free = shutil.disk_usage(STORAGE_DIR)
            usage_percent = (used / total) * 100.0
            print(f"[RetentionManager] Disk usage at: {usage_percent:.2f}% (Limit: {self.max_disk_usage_percent}%)")
            
            if usage_percent > self.max_disk_usage_percent:
                print(f"[RetentionManager] Disk usage ({usage_percent:.2f}%) exceeds limit of {self.max_disk_usage_percent}%. Pruning oldest files...")
                # Sort remaining files by mtime (oldest first)
                unprotected_files.sort(key=lambda x: x["mtime"])
                
                for file_info in unprotected_files:
                    try:
                        os.remove(file_info["filepath"])
                        print(f"[RetentionManager] Disk threshold exceeded. Pruned oldest recording: {file_info['camera_id']}/{file_info['filename']} (mtime: {file_info['mtime'].strftime('%Y-%m-%d %H:%M:%S')})")
                        # Recalculate usage
                        total, used, free = shutil.disk_usage(STORAGE_DIR)
                        usage_percent = (used / total) * 100.0
                        if usage_percent <= self.max_disk_usage_percent:
                            print(f"[RetentionManager] Disk usage reduced to {usage_percent:.2f}%. Pruning stopped.")
                            break
                    except OSError as e:
                        print(f"[RetentionManager] Error pruning {file_info['filepath']}: {e}")
        finally:
            db.close()

# Global Instance
retention_manager = RetentionManager()
