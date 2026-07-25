import numpy as np


class AbandonedObjectDetector:
    """
    Monitors bags (backpack, handbag, suitcase) to detect when an owner
    leaves the object unattended.

    Proximity is measured in **pixel distance** (not normalized), so
    PROXIMITY_THRESHOLD_PX should be set to a reasonable pixel value
    (e.g. 120 px at 640-wide frames, scale up for higher resolutions).
    """

    BAG_CLASSES = {"backpack", "handbag", "suitcase"}
    PROXIMITY_THRESHOLD_PX = 120   # pixels — owner must be within this distance
    STATIONARY_SPEED_THRESHOLD = 2.0  # pixels/frame EMA speed considered "stationary"
    FRAMES_TO_CONFIRM = 5          # consecutive frames bag must be unattended before alert

    def __init__(
        self,
        proximity_threshold_px: float = PROXIMITY_THRESHOLD_PX,
        stationary_threshold: float = STATIONARY_SPEED_THRESHOLD,
        frames_to_confirm: int = FRAMES_TO_CONFIRM,
    ):
        # bag_track_id -> { "owner_id", "stationary_count", "alert_triggered" }
        self.bag_states = {}
        self.proximity_threshold_px = proximity_threshold_px
        self.stationary_threshold = stationary_threshold
        self.frames_to_confirm = frames_to_confirm

    def check(self, tracks: list) -> tuple:
        """
        tracks: list of active track dicts with keys:
            track_id, label, bbox [x1,y1,x2,y2], speed

        Returns: (triggered: bool, message: str)
        """
        bags = [t for t in tracks if t["label"] in self.BAG_CLASSES]
        people = [t for t in tracks if t["label"] == "person"]

        for bag in bags:
            bid = bag["track_id"]
            bbox = bag["bbox"]
            bcx = (bbox[0] + bbox[2]) / 2.0
            bcy = (bbox[1] + bbox[3]) / 2.0

            if bid not in self.bag_states:
                # Find closest person (pixel distance)
                closest_id = None
                min_dist = float("inf")

                for person in people:
                    pbox = person["bbox"]
                    pcx = (pbox[0] + pbox[2]) / 2.0
                    pcy = (pbox[1] + pbox[3]) / 2.0
                    dist = np.sqrt((bcx - pcx) ** 2 + (bcy - pcy) ** 2)
                    if dist < min_dist:
                        min_dist = dist
                        closest_id = person["track_id"]

                # Associate bag with owner if within pixel threshold
                if closest_id is not None and min_dist < self.proximity_threshold_px:
                    self.bag_states[bid] = {
                        "owner_id": closest_id,
                        "stationary_count": 0,
                        "alert_triggered": False,
                    }
            else:
                state = self.bag_states[bid]
                if state["alert_triggered"]:
                    continue

                # Check if owner is still nearby (pixel distance)
                owner_nearby = False
                for person in people:
                    if person["track_id"] == state["owner_id"]:
                        pbox = person["bbox"]
                        pcx = (pbox[0] + pbox[2]) / 2.0
                        pcy = (pbox[1] + pbox[3]) / 2.0
                        dist = np.sqrt((bcx - pcx) ** 2 + (bcy - pcy) ** 2)
                        if dist < self.proximity_threshold_px:
                            owner_nearby = True
                        break

                bag_speed = bag.get("speed", 0.0)
                if not owner_nearby and bag_speed < self.stationary_threshold:
                    state["stationary_count"] += 1
                    if state["stationary_count"] >= self.frames_to_confirm:
                        state["alert_triggered"] = True
                        msg = (
                            f"Abandoned object alert: Unattended {bag['label']} "
                            f"(Track ID {bid}) detected. Owner "
                            f"(Person ID {state['owner_id']}) is no longer nearby."
                        )
                        return True, msg
                else:
                    # Owner returned or bag is moving — reset counter
                    state["stationary_count"] = max(0, state["stationary_count"] - 1)

        # Cleanup states for inactive bags
        active_bag_ids = {b["track_id"] for b in bags}
        for bid in [k for k in self.bag_states if k not in active_bag_ids]:
            del self.bag_states[bid]

        return False, ""
