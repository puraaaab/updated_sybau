import time
from .restricted import RestrictedAreaDetector
from .loitering import LoiteringDetector
from .running import RunningDetector
from .crowd import CrowdDensityDetector
from .wrong_direction import WrongDirectionDetector
from .abandoned_object import AbandonedObjectDetector

class BehaviorEngine:
    def __init__(self, default_cooldown_seconds: float = 30.0):
        self.restricted_detector = RestrictedAreaDetector()
        self.loitering_detector = LoiteringDetector()
        self.running_detector = RunningDetector()
        self.crowd_detector = CrowdDensityDetector()
        self.wrong_direction_detector = WrongDirectionDetector()
        self.abandoned_detector = AbandonedObjectDetector()
        self.default_cooldown_seconds = default_cooldown_seconds
        self._alert_cooldown_history = {} # (track_id, alert_type, key) -> timestamp

    def _should_emit_alert(self, track_id: int | str, alert_type: str, sub_key: str, cooldown_seconds: float) -> bool:
        """Enforces a sliding window cooldown per (track_id, alert_type, sub_key) to eliminate alert storms."""
        now = time.time()
        dedup_key = (str(track_id), alert_type, str(sub_key))
        
        # Periodic pruning of stale history entries (>10 mins)
        if len(self._alert_cooldown_history) > 500:
            self._alert_cooldown_history = {
                k: ts for k, ts in self._alert_cooldown_history.items()
                if (now - ts) < 600.0
            }

        last_ts = self._alert_cooldown_history.get(dedup_key, 0.0)
        if (now - last_ts) < cooldown_seconds:
            return False

        self._alert_cooldown_history[dedup_key] = now
        return True

    def check_behaviors(self, tracks: list, zones: list, alerts_cfg: dict, frame_width: float = 1920.0, frame_height: float = 1080.0) -> list:
        """
        Orchestrates all behavior checks on the active object tracks.
        Each check only runs if explicitly enabled in alerts_cfg (e.g. {"loitering": {"enabled": true, ...}}).

        Args:
            tracks:       Active detection+tracking results for this frame.
            zones:        Zone definitions (points stored as normalized 0-1 coords).
            alerts_cfg:   Alert threshold configuration dict.
            frame_width:  Pixel width of the source frame (for coord normalization).
            frame_height: Pixel height of the source frame (for coord normalization).

        Returns:
            List of dicts representing triggered alerts after deduplication cooldown.
        """
        triggered_alerts = []
        active_track_ids = [t["track_id"] for t in tracks]

        # Cleanup loitering stale tracks
        self.loitering_detector.cleanup_stale_tracks(active_track_ids)

        cooldown_sec = alerts_cfg.get("cooldown_seconds", self.default_cooldown_seconds) if isinstance(alerts_cfg, dict) else self.default_cooldown_seconds

        loitering_cfg  = alerts_cfg.get("loitering", {})  if isinstance(alerts_cfg, dict) else {}
        running_cfg    = alerts_cfg.get("running", {})    if isinstance(alerts_cfg, dict) else {}
        crowd_cfg      = alerts_cfg.get("crowd", {})      if isinstance(alerts_cfg, dict) else {}
        restricted_cfg = alerts_cfg.get("restricted", {}) if isinstance(alerts_cfg, dict) else {}
        wdir_cfg       = alerts_cfg.get("wrong_direction", {}) if isinstance(alerts_cfg, dict) else {}
        abandoned_cfg  = alerts_cfg.get("abandoned", {})  if isinstance(alerts_cfg, dict) else {}

        loitering_enabled  = loitering_cfg.get("enabled", False)
        running_enabled    = running_cfg.get("enabled", False)
        crowd_enabled      = crowd_cfg.get("enabled", False)
        restricted_enabled = restricted_cfg.get("enabled", False)
        wdir_enabled       = wdir_cfg.get("enabled", False)
        abandoned_enabled  = abandoned_cfg.get("enabled", False)

        loitering_sec  = loitering_cfg.get("time_threshold_seconds", 10.0)
        running_speed  = running_cfg.get("speed_threshold_pixels_per_second", 150.0)
        crowd_limit    = crowd_cfg.get("density_threshold", 5)

        # Run individual track checks
        for track in tracks:
            t_id = track.get("track_id", "unknown")

            # A. Restricted Area Check
            if restricted_enabled:
                res_trigger, res_msg = self.restricted_detector.check(track, zones, frame_width, frame_height)
                if res_trigger and self._should_emit_alert(t_id, "restricted", res_msg, cooldown_sec):
                    triggered_alerts.append({
                        "type": "restricted",
                        "message": res_msg,
                        "severity": "high"
                    })

            # B. Loitering Area Check
            if loitering_enabled:
                loit_trigger, loit_msg = self.loitering_detector.check(track, zones, loitering_sec, frame_width, frame_height)
                if loit_trigger and self._should_emit_alert(t_id, "loitering", loit_msg, cooldown_sec):
                    triggered_alerts.append({
                        "type": "loitering",
                        "message": loit_msg,
                        "severity": "medium"
                    })

            # C. Running Check
            if running_enabled:
                run_trigger, run_msg = self.running_detector.check(track, running_speed)
                if run_trigger and self._should_emit_alert(t_id, "running", run_msg, cooldown_sec):
                    triggered_alerts.append({
                        "type": "running",
                        "message": run_msg,
                        "severity": "low"
                    })

            # D. Wrong Direction Line Crossing Check
            if wdir_enabled:
                wdir_trigger, wdir_msg = self.wrong_direction_detector.check(track, zones)
                if wdir_trigger and self._should_emit_alert(t_id, "wrong_direction", wdir_msg, cooldown_sec):
                    triggered_alerts.append({
                        "type": "wrong_direction",
                        "message": wdir_msg,
                        "severity": "high"
                    })

        # 4. Crowd Density Checks (Zone-wide / Global)
        if crowd_enabled:
            crowd_alerts = self.crowd_detector.check(tracks, zones, crowd_limit, frame_width, frame_height)
            for trig, msg in crowd_alerts:
                if trig and self._should_emit_alert("global", "crowd", msg, cooldown_sec):
                    triggered_alerts.append({
                        "type": "crowd",
                        "message": msg,
                        "severity": "medium"
                    })

        # 5. Abandoned Object Check
        if abandoned_enabled:
            ab_trig, ab_msg = self.abandoned_detector.check(tracks)
            if ab_trig and self._should_emit_alert("global", "abandoned", ab_msg, cooldown_sec):
                triggered_alerts.append({
                    "type": "abandoned",
                    "message": ab_msg,
                    "severity": "high"
                })

        return triggered_alerts

# Global Engine Instance
behavior_engine = BehaviorEngine()

