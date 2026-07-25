class RunningDetector:
    def check(self, track_info: dict, speed_threshold: float) -> tuple:
        """
        Detects if a pedestrian is running by monitoring tracking speed metrics.
        Returns: (triggered: bool, message: str)
        """
        # Running alerts only apply to pedestrians (persons)
        if track_info["label"] != "person":
            return False, ""
            
        speed = track_info.get("speed", 0.0)
        
        # If speed exceeds threshold, trigger alert
        if speed > speed_threshold:
            msg = f"Person (ID {track_info['track_id']}) detected running at high speed ({int(speed)} px/sec)"
            return True, msg
            
        return False, ""
