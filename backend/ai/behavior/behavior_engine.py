from .restricted import RestrictedAreaDetector
from .loitering import LoiteringDetector
from .running import RunningDetector
from .crowd import CrowdDensityDetector
from .wrong_direction import WrongDirectionDetector
from .abandoned_object import AbandonedObjectDetector

class BehaviorEngine:
    def __init__(self):
        self.restricted_detector = RestrictedAreaDetector()
        self.loitering_detector = LoiteringDetector()
        self.running_detector = RunningDetector()
        self.crowd_detector = CrowdDensityDetector()
        self.wrong_direction_detector = WrongDirectionDetector()
        self.abandoned_detector = AbandonedObjectDetector()

    def check_behaviors(self, tracks: list, zones: list, alerts_cfg: dict, frame_width: float = 1920.0, frame_height: float = 1080.0) -> list:
        """
        Orchestrates all behavior checks on the active object tracks.

        Args:
            tracks:       Active detection+tracking results for this frame.
            zones:        Zone definitions (points stored as normalized 0-1 coords).
            alerts_cfg:   Alert threshold configuration dict.
            frame_width:  Pixel width of the source frame (for coord normalization).
            frame_height: Pixel height of the source frame (for coord normalization).

        Returns:
            List of dicts representing triggered alerts.
        """
        triggered_alerts = []
        active_track_ids = [t["track_id"] for t in tracks]

        # Cleanup loitering stale tracks
        self.loitering_detector.cleanup_stale_tracks(active_track_ids)

        # 1. Check loitering threshold
        loitering_sec = alerts_cfg.get("loitering", {}).get("time_threshold_seconds", 10.0)

        # 2. Check running threshold
        running_speed = alerts_cfg.get("running", {}).get("speed_threshold_pixels_per_second", 150.0)

        # 3. Check crowd density
        crowd_limit = alerts_cfg.get("crowd", {}).get("density_threshold", 5)

        # Run individual track checks
        for track in tracks:
            # A. Restricted Area Check
            res_trigger, res_msg = self.restricted_detector.check(track, zones, frame_width, frame_height)
            if res_trigger:
                triggered_alerts.append({
                    "type": "restricted",
                    "message": res_msg,
                    "severity": "high"
                })

            # B. Loitering Area Check
            loit_trigger, loit_msg = self.loitering_detector.check(track, zones, loitering_sec, frame_width, frame_height)
            if loit_trigger:
                triggered_alerts.append({
                    "type": "loitering",
                    "message": loit_msg,
                    "severity": "medium"
                })

            # C. Running Check
            run_trigger, run_msg = self.running_detector.check(track, running_speed)
            if run_trigger:
                triggered_alerts.append({
                    "type": "running",
                    "message": run_msg,
                    "severity": "low"
                })

            # D. Wrong Direction Line Crossing Check
            wdir_trigger, wdir_msg = self.wrong_direction_detector.check(track, zones)
            if wdir_trigger:
                triggered_alerts.append({
                    "type": "wrong_direction",
                    "message": wdir_msg,
                    "severity": "high"
                })

        # 4. Crowd Density Checks (Zone-wide / Global)
        crowd_alerts = self.crowd_detector.check(tracks, zones, crowd_limit, frame_width, frame_height)
        for trig, msg in crowd_alerts:
            if trig:
                triggered_alerts.append({
                    "type": "crowd",
                    "message": msg,
                    "severity": "medium"
                })

        # 5. Abandoned Object Check
        ab_trig, ab_msg = self.abandoned_detector.check(tracks)
        if ab_trig:
            triggered_alerts.append({
                "type": "abandoned",
                "message": ab_msg,
                "severity": "high"
            })

        return triggered_alerts

# Global Engine Instance
behavior_engine = BehaviorEngine()
