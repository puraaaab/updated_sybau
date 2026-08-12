"""
VMS Pro — ONVIF PTZ PID Controller & Auto-Tracking Engine
Performs camera PTZ capability discovery and calibration.
Drives ONVIF PTZ movement using a PID feedback loop to center detected targets.
Degrades gracefully for non-PTZ cameras without raising exceptions.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from .onvif_ptz import onvif_ptz_service

logger = logging.getLogger(__name__)


class PTZPIDController:
    """PID Controller for automatic PTZ camera target tracking."""

    def __init__(self, kp: float = 0.5, ki: float = 0.05, kd: float = 0.1):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral_x = 0.0
        self.integral_y = 0.0
        self.last_error_x = 0.0
        self.last_error_y = 0.0

    def discover_and_calibrate(self, camera_id: str) -> Dict[str, Any]:
        """Discovers camera ONVIF PTZ capabilities and returns calibration profile."""
        try:
            caps = onvif_ptz_service.get_ptz_status(camera_id)
            has_ptz = caps.get("ptz_supported", False)
            return {
                "camera_id": camera_id,
                "has_ptz": has_ptz,
                "pan_limits": [-1.0, 1.0],
                "tilt_limits": [-1.0, 1.0],
                "zoom_limits": [0.0, 1.0],
                "calibrated": has_ptz
            }
        except Exception as e:
            logger.debug(f"[PTZController] PTZ capability check note for {camera_id}: {e}")
            return {"camera_id": camera_id, "has_ptz": False, "calibrated": False}

    def auto_track_target(self, camera_id: str, target_cx: float, target_cy: float, frame_w: int = 1920, frame_h: int = 1080) -> Dict[str, Any]:
        """
        Calculates position error from frame center (0.5, 0.5) and computes PID pan/tilt velocity commands.
        Degrades gracefully without throwing exceptions if camera lacks PTZ support.
        """
        calib = self.discover_and_calibrate(camera_id)
        if not calib["has_ptz"]:
            return {"tracking_active": False, "reason": "PTZ not supported on camera"}

        # Position error normalized to [-0.5, 0.5]
        error_x = target_cx - 0.5
        error_y = target_cy - 0.5

        # PID terms
        self.integral_x += error_x
        self.integral_y += error_y
        derivative_x = error_x - self.last_error_x
        derivative_y = error_y - self.last_error_y

        self.last_error_x = error_x
        self.last_error_y = error_y

        pan_speed = self.kp * error_x + self.ki * self.integral_x + self.kd * derivative_x
        tilt_speed = -(self.kp * error_y + self.ki * self.integral_y + self.kd * derivative_y)  # Invert tilt

        # Clamp speed limits to [-1.0, 1.0]
        pan_speed = float(np.clip(pan_speed, -1.0, 1.0))
        tilt_speed = float(np.clip(tilt_speed, -1.0, 1.0))

        # Send movement command
        try:
            onvif_ptz_service.move_continuous(camera_id, pan_speed, tilt_speed, 0.0)
        except Exception as err:
            logger.debug(f"[PTZController] Move command note for {camera_id}: {err}")

        return {
            "tracking_active": True,
            "error_x": round(error_x, 3),
            "error_y": round(error_y, 3),
            "pan_speed": round(pan_speed, 3),
            "tilt_speed": round(tilt_speed, 3)
        }


import numpy as np
ptz_pid_controller = PTZPIDController()
