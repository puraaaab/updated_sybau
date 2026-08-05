import datetime
from .restricted import is_point_in_polygon

class LoiteringDetector:
    def __init__(self):
        # track_id -> entry_time (datetime)
        self.track_entry_times = {}

    def check(self, track_info: dict, zones: list, threshold_seconds: float, frame_width: float = 1920.0, frame_height: float = 1080.0) -> tuple:
        """
        Checks if an object has remained inside a loitering zone for too long.
        Zone points are normalized (0-1); bbox coords are pixels.
        Returns: (triggered: bool, message: str)
        """
        bbox = track_info["bbox"]
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = bbox[3]

        track_id = track_info["track_id"]
        now = datetime.datetime.now(datetime.timezone.utc)

        in_loitering_zone = False
        active_zone_name = ""

        for zone in zones:
            if zone["type"] == "loitering":
                if is_point_in_polygon(cx, cy, zone["points"], frame_width, frame_height):
                    in_loitering_zone = True
                    active_zone_name = zone["name"]
                    break
                    
        if in_loitering_zone:
            if track_id not in self.track_entry_times:
                self.track_entry_times[track_id] = now
            else:
                elapsed = (now - self.track_entry_times[track_id]).total_seconds()
                if elapsed > threshold_seconds:
                    # Loitering triggered
                    msg = f"{track_info['label'].capitalize()} (ID {track_id}) loitering in {active_zone_name} for {int(elapsed)} seconds"
                    return True, msg
        else:
            # If object leaves the zone, reset timer
            if track_id in self.track_entry_times:
                del self.track_entry_times[track_id]
                
        return False, ""
        
    def cleanup_stale_tracks(self, active_track_ids: list):
        stale_ids = [tid for tid in self.track_entry_times if tid not in active_track_ids]
        for tid in stale_ids:
            del self.track_entry_times[tid]
