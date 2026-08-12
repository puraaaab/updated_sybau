"""
VMS Pro — Adaptive Frame Governor
Regulates frame sampling rates (MIN_FPS, TARGET_FPS, MAX_FPS) dynamically per camera
and AI skill based on GPU inference queue depth backpressure.
"""

import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AdaptiveFrameGovernor:
    """
    Monitors GPU queue depth and activity state to adaptively compute target frame sampling rate.
    
    Logic:
    - Normal state: TARGET_FPS (default 2-3 FPS)
    - Motion / Object active: Boost to 5 FPS
    - Critical event: Boost to MAX_FPS (10 FPS)
    - GPU Queue Backpressure High (>80% capacity): Scale down to MIN_FPS (1 FPS)
    """

    def __init__(self, min_fps: float = 1.0, target_fps: float = 3.0, max_fps: float = 10.0):
        self.min_fps = min_fps
        self.target_fps = target_fps
        self.max_fps = max_fps
        self._last_sampling_time: Dict[str, float] = {}

    def calculate_sampling_rate(
        self,
        camera_id: str,
        inference_queue_depth: int,
        inference_queue_max: int,
        has_motion: bool = False,
        is_critical_event: bool = False
    ) -> float:
        # Check backpressure
        queue_fill_ratio = (inference_queue_depth / float(max(1, inference_queue_max)))
        
        if queue_fill_ratio > 0.8:
            # High backpressure -> throttle down to MIN_FPS
            effective_fps = self.min_fps
        elif is_critical_event:
            # Critical event -> scale up to MAX_FPS
            effective_fps = self.max_fps
        elif has_motion:
            # Motion active -> scale up to middle boost
            effective_fps = min(self.max_fps, self.target_fps * 1.5)
        else:
            effective_fps = self.target_fps

        return effective_fps

    def should_sample_frame(
        self,
        camera_id: str,
        inference_queue_depth: int = 0,
        inference_queue_max: int = 50,
        has_motion: bool = False,
        is_critical: bool = False
    ) -> bool:
        """Determines whether current timestamp satisfies the calculated adaptive frame interval."""
        now = time.time()
        last_time = self._last_sampling_time.get(camera_id, 0.0)
        
        target_fps = self.calculate_sampling_rate(
            camera_id=camera_id,
            inference_queue_depth=inference_queue_depth,
            inference_queue_max=inference_queue_max,
            has_motion=has_motion,
            is_critical_event=is_critical
        )
        
        frame_interval = 1.0 / max(0.1, target_fps)
        if (now - last_time) >= frame_interval:
            self._last_sampling_time[camera_id] = now
            return True
        return False


frame_governor = AdaptiveFrameGovernor()
