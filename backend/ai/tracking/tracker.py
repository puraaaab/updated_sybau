import datetime
import threading

import numpy as np


class TrajectoryTracker:
    def __init__(self, history_len=30, stale_seconds=5.0):
        self.history_len = history_len
        self.stale_seconds = stale_seconds
        # Keyed by (camera_id, track_id) — ByteTrack IDs are only unique
        # *within* a single camera's tracker instance. Keying by track_id
        # alone caused tracks from different cameras with the same numeric
        # ID to overwrite each other's path/speed history.
        self.active_tracks = {}
        self._lock = threading.Lock()

    def update_tracks(self, detections, camera_id):
        """
        Updates tracking paths, calculates speeds, and updates first/last seen timestamps.
        detections: list of dicts from detect_and_track
        Returns:
            Updated tracks dictionary containing path history and speed.
        """
        from ...utils.timezone import get_ist_now
        now = get_ist_now()
        updated_detections = []

        with self._lock:
            for det in detections:
                key = (camera_id, det["track_id"])
                bbox = det["bbox"]
                center = [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]

                if key not in self.active_tracks:
                    # New track
                    self.active_tracks[key] = {
                        "camera_id": camera_id,
                        "label": det["class_name"],
                        "first_seen": now,
                        "last_seen": now,
                        "path": [center],
                        "speed": 0.0,
                        "bbox": bbox
                    }
                else:
                    # Existing track
                    track = self.active_tracks[key]
                    prev_seen = track["last_seen"]
                    track["last_seen"] = now
                    track["bbox"] = bbox
                    track["label"] = det["class_name"]

                    # Calculate speed as pixel displacement per second, so
                    # it stays meaningful even if the processing frame rate
                    # varies (frame drops, GPU contention, etc). Guard
                    # against a zero/near-zero elapsed time.
                    prev_center = track["path"][-1]
                    displacement = np.sqrt(
                        (center[0] - prev_center[0]) ** 2 + (center[1] - prev_center[1]) ** 2
                    )
                    elapsed = max((now - prev_seen).total_seconds(), 1e-3)
                    instantaneous_speed = displacement / elapsed

                    # Dynamic speed calculation (simple exponential moving average)
                    track["speed"] = float(0.7 * track["speed"] + 0.3 * instantaneous_speed)

                    track["path"].append(center)
                    if len(track["path"]) > self.history_len:
                        track["path"].pop(0)

                # Decorate the detection object with trajectory info for downstream modules
                det_copy = det.copy()
                det_copy["label"] = det["class_name"]
                det_copy["camera_id"] = camera_id
                det_copy["track_uuid"] = f"TRK_{camera_id}_{det['track_id']}"
                det_copy["speed"] = self.active_tracks[key]["speed"]
                det_copy["path"] = self.active_tracks[key]["path"]
                updated_detections.append(det_copy)

            # Clean up stale tracks (not updated recently)
            stale_keys = [
                k for k, tinfo in self.active_tracks.items()
                if (now - tinfo["last_seen"]).total_seconds() > self.stale_seconds
            ]
            for k in stale_keys:
                del self.active_tracks[k]

        return updated_detections


# Global tracker instance
trajectory_tracker = TrajectoryTracker()