"""
Traffic Analytics & Speed Estimation Engine — Computes vehicle speeds (km/h) and directional compliance.
"""

import math
from typing import List, Dict, Tuple

PIXELS_PER_METER_DEFAULT = 15.0  # Default camera calibration scale ratio

def calculate_speed_kmh(p1: Tuple[float, float], p2: Tuple[float, float], time_delta_sec: float, px_per_meter: float = PIXELS_PER_METER_DEFAULT) -> float:
    """
    Calculates speed in km/h based on pixel displacement over time_delta_sec.
    """
    if time_delta_sec <= 0 or px_per_meter <= 0:
        return 0.0
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist_px = math.sqrt(dx * dx + dy * dy)
    dist_m = dist_px / px_per_meter
    speed_mps = dist_m / time_delta_sec
    speed_kmh = speed_mps * 3.6
    return round(speed_kmh, 1)


def check_directional_compliance(movement_vec: Tuple[float, float], allowed_direction_vec: Tuple[float, float]) -> bool:
    """
    Computes cosine similarity between object movement vector and allowed zone direction vector.
    Returns True if compliant, False if wrong-way driving (cosine angle < -0.3).
    """
    mx, my = movement_vec
    ax, ay = allowed_direction_vec
    mag_m = math.sqrt(mx * mx + my * my)
    mag_a = math.sqrt(ax * ax + ay * ay)
    if mag_m == 0 or mag_a == 0:
        return True  # Stationary

    dot = (mx * ax + my * ay)
    cos_sim = dot / (mag_m * mag_a)
    return cos_sim >= -0.3


def compute_traffic_analytics(tracks: List[dict], direction_vector: Tuple[float, float] = (1.0, 0.0)) -> dict:
    """
    Analyzes active tracks to produce vehicle count, speed distributions, and direction compliance.
    """
    total_vehicles = len(tracks)
    speeds = []
    wrong_way_count = 0

    for tr in tracks:
        speed = tr.get("speed", 0.0)
        # Convert m/s or pixel speed to km/h if needed
        speed_kmh = round(speed * 3.6 if speed < 40.0 else speed, 1)
        speeds.append(speed_kmh)

        # Vector direction check
        history = tr.get("path_history", [])
        if len(history) >= 2:
            p1 = history[0]
            p2 = history[-1]
            move_vec = (p2[0] - p1[0], p2[1] - p1[1])
            if not check_directional_compliance(move_vec, direction_vector):
                wrong_way_count += 1

    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0
    max_speed = max(speeds) if speeds else 0.0

    return {
        "total_vehicles_count": total_vehicles,
        "average_speed_kmh": avg_speed,
        "max_speed_kmh": max_speed,
        "wrong_direction_violations": wrong_way_count,
        "speed_distribution": speeds
    }
