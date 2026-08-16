"""
Abandoned / Unattended Object Detection Engine (Prompt 9.2).
Zero new GPU models: Uses YOLO COCO classes ('backpack', 'handbag', 'suitcase')
with bounding-box spatial tracking and track-separation distance math.
"""
from typing import Dict, List, Optional, Tuple, Any
import math
import time
import datetime


class TrackedItemState:
    def __init__(self, track_id: str, class_name: str, bbox: List[float], timestamp: float):
        self.track_id = track_id
        self.class_name = class_name
        self.first_seen = timestamp
        self.last_seen = timestamp
        self.initial_bbox = bbox
        self.current_bbox = bbox
        self.is_stationary = True
        self.last_alert_time = 0.0

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.current_bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def dwell_seconds(self) -> float:
        return max(0.0, self.last_seen - self.first_seen)


class AbandonedObjectDetector:
    """
    Evaluates stationary object bounding boxes against nearby person tracks.
    If an item remains stationary for >= dwell_time_sec and no person is within
    owner_distance_pixels, triggers an ABANDONED_OBJECT event.
    """
    TARGET_CLASSES = {"backpack", "suitcase", "handbag", "bag", "luggage", "box"}

    def __init__(
        self,
        dwell_time_sec: float = 60.0,
        owner_distance_pixels: float = 150.0,
        max_displacement_pixels: float = 30.0,
        alert_cooldown_sec: float = 60.0,
    ):
        self.dwell_time_sec = dwell_time_sec
        self.owner_distance_pixels = owner_distance_pixels
        self.max_displacement_pixels = max_displacement_pixels
        self.alert_cooldown_sec = alert_cooldown_sec
        # camera_id -> {track_id: TrackedItemState}
        self.active_items: Dict[str, Dict[str, TrackedItemState]] = {}

    def _distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def process_frame_detections(
        self,
        camera_id: str,
        detections: List[Dict[str, Any]],
        current_timestamp: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Args:
            camera_id: Identifier of the camera stream
            detections: List of dicts, each having:
                - 'track_id': str/int
                - 'class_name': str ('backpack', 'person', etc.)
                - 'bbox': [x1, y1, x2, y2]
                - 'confidence': float
            current_timestamp: Unix epoch timestamp in seconds (default time.time())

        Returns:
            List of generated alert dicts for newly triggered abandoned objects.
        """
        if current_timestamp is None:
            current_timestamp = time.time()

        if camera_id not in self.active_items:
            self.active_items[camera_id] = {}

        camera_state = self.active_items[camera_id]

        person_centers: List[Tuple[float, float]] = []
        luggage_detections: List[Dict[str, Any]] = []

        for det in detections:
            cname = str(det.get("class_name", "")).lower()
            bbox = det.get("bbox", [0, 0, 0, 0])
            if cname == "person":
                cx = (bbox[0] + bbox[2]) / 2.0
                cy = (bbox[1] + bbox[3]) / 2.0
                person_centers.append((cx, cy))
            elif cname in self.TARGET_CLASSES:
                luggage_detections.append(det)

        alerts: List[Dict[str, Any]] = []
        active_track_ids = set()

        for det in luggage_detections:
            track_id = str(det.get("track_id", ""))
            if not track_id:
                continue
            active_track_ids.add(track_id)
            cname = str(det.get("class_name", "bag")).lower()
            bbox = det.get("bbox", [0, 0, 0, 0])

            if track_id not in camera_state:
                camera_state[track_id] = TrackedItemState(
                    track_id=track_id,
                    class_name=cname,
                    bbox=bbox,
                    timestamp=current_timestamp,
                )
            else:
                item = camera_state[track_id]
                item.last_seen = current_timestamp
                # Check displacement from initial center
                init_cx = (item.initial_bbox[0] + item.initial_bbox[2]) / 2.0
                init_cy = (item.initial_bbox[1] + item.initial_bbox[3]) / 2.0
                curr_cx = (bbox[0] + bbox[2]) / 2.0
                curr_cy = (bbox[1] + bbox[3]) / 2.0
                displacement = math.hypot(curr_cx - init_cx, curr_cy - init_cy)

                if displacement > self.max_displacement_pixels:
                    # Item moved significantly, reset stationary tracking
                    item.initial_bbox = bbox
                    item.first_seen = current_timestamp
                    item.is_stationary = False
                else:
                    item.is_stationary = True

                item.current_bbox = bbox

                # Evaluate abandoned condition
                if item.is_stationary and item.dwell_seconds >= self.dwell_time_sec:
                    # Check distance to nearest person
                    min_dist_to_person = float("inf")
                    for pc in person_centers:
                        d = self._distance(item.center, pc)
                        if d < min_dist_to_person:
                            min_dist_to_person = d

                    # If no person nearby (unattended)
                    if min_dist_to_person > self.owner_distance_pixels:
                        if current_timestamp - item.last_alert_time >= self.alert_cooldown_sec:
                            item.last_alert_time = current_timestamp
                            dwell_min = round(item.dwell_seconds / 60.0, 1)
                            alert_obj = {
                                "type": "ABANDONED_OBJECT",
                                "event_type": "ABANDONED_OBJECT",
                                "severity": "HIGH",
                                "camera_id": camera_id,
                                "class_name": item.class_name,
                                "track_id": item.track_id,
                                "dwell_seconds": round(item.dwell_seconds, 1),
                                "dwell_minutes": dwell_min,
                                "nearest_person_dist_px": round(min_dist_to_person, 1) if min_dist_to_person != float("inf") else 999.0,
                                "bbox": item.current_bbox,
                                "details": f"Unattended {item.class_name.upper()} (Track #{item.track_id}) stationary for {int(item.dwell_seconds)}s with no owner within {int(self.owner_distance_pixels)}px.",
                                "confidence": det.get("confidence", 0.95),
                                "timestamp": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat(),
                            }
                            alerts.append(alert_obj)

        # Cleanup stale tracks
        stale_tracks = [tid for tid, item in camera_state.items() if current_timestamp - item.last_seen > 30.0]
        for tid in stale_tracks:
            del camera_state[tid]

        return alerts


# Singleton instance
abandoned_object_detector = AbandonedObjectDetector()
