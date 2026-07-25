from .restricted import is_point_in_polygon

class CrowdDensityDetector:
    def __init__(self):
        self.count_history = []  # rolling history of (timestamp, count)

    def check(self, tracks: list, zones: list, density_threshold: int, frame_width: float = 1920.0, frame_height: float = 1080.0) -> list:
        """
        Counts total number of persons in each zone and checks for rapid crowd surges.
        Returns: list of tuples (triggered: bool, message: str) for any violations.
        """
        people = [t for t in tracks if t["label"] == "person"]
        alerts = []
        global_count = len(people)

        # Use Case 4: Rapid Crowd Surge Rate-of-Change Detection
        self.count_history.append(global_count)
        if len(self.count_history) > 30:
            self.count_history.pop(0)

        # If count increased significantly over rolling window (surge)
        if len(self.count_history) >= 10:
            initial_count = self.count_history[0]
            if global_count - initial_count >= 5 and global_count >= density_threshold:
                surge_msg = f"HIGH RISK CROWD SURGE: Rapid overcrowding detected ({initial_count} → {global_count} persons)."
                alerts.append((True, surge_msg))

        # Calculate for each zone
        for zone in zones:
            if zone["type"] in ["restricted", "loitering", "pedestrian_zone"]:
                count = 0
                points = zone["points"]
                for person in people:
                    bbox = person["bbox"]
                    cx = (bbox[0] + bbox[2]) / 2.0
                    cy = bbox[3]
                    if is_point_in_polygon(cx, cy, points, frame_width, frame_height):
                        count += 1
                        
                if count >= density_threshold:
                    msg = f"Crowd alert: {count} persons gathered in zone '{zone['name']}' (limit: {density_threshold})"
                    alerts.append((True, msg))
                    
        # Also check global count across camera stream if no zone triggers
        if len(zones) == 0 and global_count >= density_threshold:
            msg = f"High global crowd density: {global_count} persons detected in stream (limit: {density_threshold})"
            alerts.append((True, msg))
            
        return alerts
