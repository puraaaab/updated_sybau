import os
import sys
import cv2

# Add repository root to PYTHONPATH for absolute imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(ROOT_DIR)

from backend.ai.pipeline.orchestrator import process_frame
from backend.ai.scheduler import inference_scheduler
# Increase scheduler timeout only for reindexing (600 s); will be reset afterwards
inference_scheduler.TASK_TIMEOUT_SECONDS = 600
from backend.config.service import get_zones, get_alerts

# Path to recordings directory (adjust if needed)
RECORDINGS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage', 'recordings'))

def get_all_video_files(root_path):
    video_exts = {'.mp4', '.avi', '.mov', '.mkv'}
    files = []
    for dirpath, _, filenames in os.walk(root_path):
        for f in filenames:
            if os.path.splitext(f)[1].lower() in video_exts:
                files.append(os.path.join(dirpath, f))
    return files

def reindex_video(video_path, camera_id):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[Reindex] Cannot open video: {video_path}")
        return
    frame_idx = 0
    zones_dict = get_zones()
    zones = zones_dict.get(camera_id, [])  # Convert to list for this camera
    alerts_cfg = get_alerts()
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Run the existing pipeline on each frame (this will upsert vectors to Qdrant)
        _ = process_frame(frame, camera_id, zones, alerts_cfg, frame_idx)
        frame_idx += 1
    cap.release()
    print(f"[Reindex] Completed {video_path} (processed {frame_idx} frames)")

def main():
    video_files = get_all_video_files(RECORDINGS_ROOT)
    if not video_files:
        print("[Reindex] No video files found.")
        return
    inference_scheduler.start()
    for video_path in video_files:
        # Use the top‑level subdirectory under recordings as the camera identifier
        rel_path = os.path.relpath(video_path, RECORDINGS_ROOT)
        parts = rel_path.split(os.sep)
        camera_id = parts[0] if parts else 'unknown'
        reindex_video(video_path, camera_id)
    inference_scheduler.stop()
    inference_scheduler.TASK_TIMEOUT_SECONDS = 120
    print("[Reindex] All videos processed.")

if __name__ == '__main__':
    main()
