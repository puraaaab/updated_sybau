"""
VMS Pro — AI Skill Registry & Adapter Architecture
Standardized AISkill interface for per-camera skill allocation, model versioning,
min/target/max FPS rules, hardware requirements, and health telemetry.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class AISkill(ABC):
    """Abstract Base Class for all SYBAU AI Skills."""

    def __init__(
        self,
        skill_id: str,
        name: str,
        version: str,
        model_name: str,
        input_type: str = "frame",
        min_fps: float = 1.0,
        target_fps: float = 5.0,
        max_fps: float = 10.0,
        hardware_req: str = "CPU",
        confidence_threshold: float = 0.50
    ):
        self.skill_id = skill_id
        self.name = name
        self.version = version
        self.model_name = model_name
        self.input_type = input_type
        self.min_fps = min_fps
        self.target_fps = target_fps
        self.max_fps = max_fps
        self.hardware_req = hardware_req
        self.confidence_threshold = confidence_threshold
        self.is_healthy = True

    @abstractmethod
    def process(self, camera_id: str, input_data: Any, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Processes input frame or audio chunk and returns list of canonical event payloads."""
        pass

    @abstractmethod
    def check_health(self) -> bool:
        """Returns True if skill model is loaded and operational."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "model_name": self.model_name,
            "input_type": self.input_type,
            "min_fps": self.min_fps,
            "target_fps": self.target_fps,
            "max_fps": self.max_fps,
            "hardware_req": self.hardware_req,
            "confidence_threshold": self.confidence_threshold,
            "is_healthy": self.is_healthy
        }


class SkillRegistry:
    """Central registry managing registered AI skills and per-camera skill assignments."""

    def __init__(self):
        self._skills: Dict[str, AISkill] = {}
        self._camera_assignments: Dict[str, List[str]] = {}  # camera_id -> list of skill_ids

    def register_skill(self, skill: AISkill):
        self._skills[skill.skill_id] = skill
        logger.info(f"[SkillRegistry] Registered skill: {skill.skill_id} (v{skill.version})")

    def get_skill(self, skill_id: str) -> Optional[AISkill]:
        return self._skills.get(skill_id)

    def list_skills(self) -> List[Dict[str, Any]]:
        return [skill.to_dict() for skill in self._skills.values()]

    def assign_skill_to_camera(self, camera_id: str, skill_id: str):
        if camera_id not in self._camera_assignments:
            self._camera_assignments[camera_id] = []
        if skill_id not in self._camera_assignments[camera_id]:
            self._camera_assignments[camera_id].append(skill_id)
            logger.info(f"[SkillRegistry] Assigned skill '{skill_id}' to Camera '{camera_id}'")

    def get_camera_skills(self, camera_id: str) -> List[AISkill]:
        skill_ids = self._camera_assignments.get(camera_id, list(self._skills.keys()))
        return [self._skills[sid] for sid in skill_ids if sid in self._skills]


# Singleton instance
skill_registry = SkillRegistry()
