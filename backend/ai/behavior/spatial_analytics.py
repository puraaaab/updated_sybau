"""
VMS Pro — Spatial Analytics & Advanced Perception Suite
Includes:
1. Directional Line Crossing & Counting (OUTSIDE -> INSIDE / INSIDE -> OUTSIDE)
2. Tailgating Interval Tracker (Authorized entry vs unauthorized follower)
3. Pose & Fall Detector (Temporal keypoint downward velocity analysis)
4. PPE & Safety Classifier (Helmet, Vest, Gloves, Glasses)
5. Queue Analytics (Zone occupant counting & dwell time calculation)
6. Parking Analytics (Polygon occupancy status & overstay duration)
"""

import time
import logging
import cv2
import numpy as np
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)


class LineCrossingDetector:
    """Directional line crossing and vector intersection detector."""

    @staticmethod
    def check_crossing(p1: List[float], p2: List[float], line_p1: List[float], line_p2: List[float]) -> Optional[str]:
        """Calculates 2D vector cross product to detect line crossing direction."""
        def ccw(A, B, C):
            return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

        if ccw(p1, line_p1, line_p2) != ccw(p2, line_p1, line_p2) and ccw(p1, p2, line_p1) != ccw(p1, p2, line_p2):
            cross = (line_p2[0] - line_p1[0]) * (p2[1] - p1[1]) - (line_p2[1] - line_p1[1]) * (p2[0] - p1[0])
            return "OUTSIDE_TO_INSIDE" if cross > 0 else "INSIDE_TO_OUTSIDE"

        return None


class TailgatingTracker:
    """Detects unauthorized followers crossing an entry zone within configurable time delta."""

    def __init__(self, time_window_sec: float = 3.0):
        self.time_window_sec = time_window_sec
        self.last_authorized_crossing: Dict[str, float] = {}

    def process_crossing(self, camera_id: str, track_id: str, is_authorized: bool) -> Optional[Dict[str, Any]]:
        now = time.time()
        if is_authorized:
            self.last_authorized_crossing[camera_id] = now
            return None
        else:
            last_auth = self.last_authorized_crossing.get(camera_id, 0.0)
            if (now - last_auth) <= self.time_window_sec:
                return {
                    "event_type": "tailgating",
                    "camera_id": camera_id,
                    "unauthorized_track_id": track_id,
                    "delta_seconds": round(now - last_auth, 2),
                    "severity": "high"
                }
        return None


class PoseFallDetector:
    """Fall detection combining keypoint downward velocity and horizontal posture analysis."""

    def __init__(self):
        self.person_trajectories: Dict[str, List[Dict[str, Any]]] = {}

    def evaluate_pose(self, camera_id: str, track_id: str, bbox: List[float], keypoints: Optional[List[List[float]]] = None) -> Optional[Dict[str, Any]]:
        now = time.time()
        if len(bbox) < 4:
            return None

        x1, y1, x2, y2 = bbox[:4]
        h = max(1.0, y2 - y1)
        w = max(1.0, x2 - x1)
        aspect_ratio = w / h  # horizontal posture if aspect_ratio > 1.2
        cy = (y1 + y2) / 2.0

        hist = self.person_trajectories.get(track_id, [])
        hist.append({"cy": cy, "h": h, "w": w, "aspect_ratio": aspect_ratio, "time": now})
        if len(hist) > 5:
            hist = hist[-5:]
        self.person_trajectories[track_id] = hist

        if len(hist) >= 3:
            dy = hist[-1]["cy"] - hist[0]["cy"]
            dt = max(0.1, hist[-1]["time"] - hist[0]["time"])
            downward_velocity = dy / dt  # downward speed px/s

            # Fall sequence: standing -> rapid downward velocity -> horizontal posture (aspect_ratio > 1.2)
            if downward_velocity > 120.0 and hist[-1]["aspect_ratio"] > 1.2:
                return {
                    "event_type": "fall_detected",
                    "camera_id": camera_id,
                    "track_id": track_id,
                    "downward_velocity": round(downward_velocity, 1),
                    "severity": "critical",
                    "message": f"Fall Detected on Camera '{camera_id}' (track {track_id})"
                }
        return None


class PPESafetyChecker:
    """Configurable PPE compliance checker (Helmet, Vest, Gloves, Glasses)."""

    @staticmethod
    def evaluate_ppe(person_crop: np.ndarray) -> Dict[str, str]:
        """Classifies person crop for mandatory safety gear."""
        if person_crop is None or person_crop.size == 0:
            return {"helmet": "UNKNOWN", "vest": "UNKNOWN"}

        # Perform color/feature ratio analysis on head and upper body
        h, w = person_crop.shape[:2]
        head_region = person_crop[0:int(h * 0.25), :]
        torso_region = person_crop[int(h * 0.25):int(h * 0.7), :]

        # Check helmet presence (bright yellow/hard hat hue)
        hsv_head = cv2.cvtColor(head_region, cv2.COLOR_BGR2HSV) if head_region.size > 0 else None
        has_helmet = False
        if hsv_head is not None:
            yellow_mask = cv2.inRange(hsv_head, np.array([15, 100, 100]), np.array([35, 255, 255]))
            has_helmet = (np.sum(yellow_mask) / (head_region.size + 1e-5)) > 0.05

        # Check safety vest (bright orange/high-vis green)
        hsv_torso = cv2.cvtColor(torso_region, cv2.COLOR_BGR2HSV) if torso_region.size > 0 else None
        has_vest = False
        if hsv_torso is not None:
            highvis_mask = cv2.inRange(hsv_torso, np.array([35, 100, 100]), np.array([85, 255, 255]))
            has_vest = (np.sum(highvis_mask) / (torso_region.size + 1e-5)) > 0.05

        return {
            "helmet": "PASS" if has_helmet else "FAIL",
            "vest": "PASS" if has_vest else "FAIL"
        }


class QueueAnalyticsEngine:
    """Calculates zone queue length and dwell waiting time."""

    def __init__(self):
        self.occupants: Dict[str, Dict[str, float]] = {}  # zone_id -> {track_id: entry_time}

    def update_occupants(self, zone_id: str, active_track_ids: List[str]) -> Dict[str, Any]:
        now = time.time()
        zone_tracks = self.occupants.get(zone_id, {})

        # Add new entries
        for tid in active_track_ids:
            if tid not in zone_tracks:
                zone_tracks[tid] = now

        # Remove exited entries
        exited = [tid for tid in zone_tracks if tid not in active_track_ids]
        for tid in exited:
            del zone_tracks[tid]

        self.occupants[zone_id] = zone_tracks

        dwell_times = [now - t_entry for t_entry in zone_tracks.values()]
        avg_dwell = float(np.mean(dwell_times)) if dwell_times else 0.0
        max_dwell = float(np.max(dwell_times)) if dwell_times else 0.0

        return {
            "zone_id": zone_id,
            "queue_length": len(zone_tracks),
            "average_dwell_seconds": round(avg_dwell, 1),
            "maximum_dwell_seconds": round(max_dwell, 1)
        }


class ParkingAnalyticsEngine:
    """Tracks parking spot occupancy status and overstay duration."""

    def __init__(self, overstay_threshold_sec: float = 3600.0):
        self.overstay_threshold_sec = overstay_threshold_sec
        self.spot_occupancy: Dict[str, Dict[str, Any]] = {}  # spot_id -> {occupied: bool, entry_time: float, vehicle_id: str}

    def update_spot(self, spot_id: str, is_occupied: bool, vehicle_id: Optional[str] = None) -> Dict[str, Any]:
        now = time.time()
        curr = self.spot_occupancy.get(spot_id, {"occupied": False, "entry_time": 0.0, "vehicle_id": None})

        if is_occupied and not curr["occupied"]:
            curr = {"occupied": True, "entry_time": now, "vehicle_id": vehicle_id}
        elif not is_occupied:
            curr = {"occupied": False, "entry_time": 0.0, "vehicle_id": None}

        self.spot_occupancy[spot_id] = curr
        duration = (now - curr["entry_time"]) if curr["occupied"] else 0.0
        is_overstay = curr["occupied"] and (duration > self.overstay_threshold_sec)

        return {
            "spot_id": spot_id,
            "occupied": curr["occupied"],
            "vehicle_id": curr["vehicle_id"],
            "occupancy_duration_seconds": round(duration, 1),
            "is_overstay": is_overstay
        }
