"""
PTZ Auto-Tracking Engine — Computes pan/tilt error velocities from target bounding box centroids.
"""

from typing import Dict, Tuple, Optional

# Active tracking states per camera
_tracking_states: Dict[str, dict] = {}

def toggle_auto_tracking(camera_id: str, enabled: bool, target_id: Optional[str] = None) -> dict:
    """Toggles PTZ auto-tracking for a camera stream."""
    _tracking_states[camera_id] = {
        "enabled": enabled,
        "target_id": target_id,
        "kp_pan": 1.5,
        "kp_tilt": 1.5
    }
    return {"camera_id": camera_id, "auto_tracking": enabled, "target_id": target_id}


def is_auto_tracking_active(camera_id: str) -> bool:
    """Returns whether auto-tracking is enabled for the camera."""
    return _tracking_states.get(camera_id, {}).get("enabled", False)


def compute_ptz_error_velocities(bbox_xyxy: Tuple[float, float, float, float], frame_w: int = 1920, frame_h: int = 1080) -> Tuple[float, float]:
    """
    Computes proportional pan/tilt velocities to keep target centered.
    bbox_xyxy: (x1, y1, x2, y2)
    Returns: (pan_velocity, tilt_velocity) normalized in [-1.0, 1.0]
    """
    x1, y1, x2, y2 = bbox_xyxy
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    # Frame center
    fcx = frame_w / 2.0
    fcy = frame_h / 2.0

    # Normalized error offset in [-1.0, 1.0]
    err_x = (cx - fcx) / fcx
    err_y = (cy - fcy) / fcy

    kp = 1.2
    pan_vel = max(-1.0, min(1.0, kp * err_x))
    tilt_vel = max(-1.0, min(1.0, -kp * err_y)) # inverted tilt axis

    return round(pan_vel, 3), round(tilt_vel, 3)
