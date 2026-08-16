"""
VMS Pro — AI Skills Registry & Event Rules Router (FEAT-03)
Provides full RBAC-protected CRUD endpoints for dynamic AI skill registration,
per-camera skill assignment, and declarative multi-condition event fusion rules.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import AISkillRegistry, CameraSkillAssignment, EventRule, AuditLog, _istnow
from ..auth.helpers import verify_viewer, verify_operator, verify_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AI Skills & Event Rules"])


def _audit(db: Session, username: str, action: str, detail: str):
    try:
        log = AuditLog(
            username=username or "unknown",
            action=action,
            detail=detail,
            timestamp=_istnow()
        )
        db.add(log)
    except Exception as e:
        logger.warning(f"[Audit] Failed to log action {action}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SkillCreateSchema(BaseModel):
    skill_id: str = Field(..., min_length=2, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    version: str = Field(default="1.0.0", max_length=50)
    model_name: str = Field(..., min_length=1, max_length=255)
    input_type: str = Field(default="frame", max_length=50)
    output_schema_json: Optional[str] = "{}"
    hardware_req: str = Field(default="CPU", max_length=50)
    min_fps: float = Field(default=1.0, ge=0.1)
    target_fps: float = Field(default=5.0, ge=0.1)
    max_fps: float = Field(default=10.0, ge=0.1)
    is_enabled: bool = True


class SkillUpdateSchema(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    model_name: Optional[str] = None
    input_type: Optional[str] = None
    output_schema_json: Optional[str] = None
    hardware_req: Optional[str] = None
    min_fps: Optional[float] = None
    target_fps: Optional[float] = None
    max_fps: Optional[float] = None
    is_enabled: Optional[bool] = None


class SkillAssignmentSchema(BaseModel):
    camera_id: str = Field(..., min_length=1)
    skill_id: str = Field(..., min_length=1)
    config_json: Optional[str] = "{}"


class EventRuleCreateSchema(BaseModel):
    rule_id: str = Field(..., min_length=2, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    conditions_json: str = Field(default="[]")
    actions_json: str = Field(default="[]")
    severity: str = Field(default="high", max_length=50)
    cooldown_seconds: int = Field(default=60, ge=1)
    is_active: bool = True


class EventRuleUpdateSchema(BaseModel):
    name: Optional[str] = None
    conditions_json: Optional[str] = None
    actions_json: Optional[str] = None
    severity: Optional[str] = None
    cooldown_seconds: Optional[int] = None
    is_active: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. AI Skill Registry Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/skills")
def list_skills(
    is_enabled: Optional[bool] = Query(default=None),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Lists all registered AI Skills (RBAC: Viewer+)."""
    q = db.query(AISkillRegistry)
    if is_enabled is not None:
        q = q.filter(AISkillRegistry.is_enabled == is_enabled)
    skills = q.order_by(AISkillRegistry.id.asc()).all()
    return {
        "total": len(skills),
        "items": [
            {
                "id": s.id,
                "skill_id": s.skill_id,
                "name": s.name,
                "version": s.version,
                "model_name": s.model_name,
                "input_type": s.input_type,
                "hardware_req": s.hardware_req,
                "min_fps": s.min_fps,
                "target_fps": s.target_fps,
                "max_fps": s.max_fps,
                "is_enabled": s.is_enabled,
                "output_schema": json.loads(s.output_schema_json or "{}")
            }
            for s in skills
        ]
    }


@router.post("/skills", status_code=status.HTTP_201_CREATED)
def register_skill(
    payload: SkillCreateSchema,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Registers a new AI skill into the registry (RBAC: Admin)."""
    existing = db.query(AISkillRegistry).filter(AISkillRegistry.skill_id == payload.skill_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Skill '{payload.skill_id}' already registered.")

    skill = AISkillRegistry(
        skill_id=payload.skill_id,
        name=payload.name,
        version=payload.version,
        model_name=payload.model_name,
        input_type=payload.input_type,
        output_schema_json=payload.output_schema_json or "{}",
        hardware_req=payload.hardware_req,
        min_fps=payload.min_fps,
        target_fps=payload.target_fps,
        max_fps=payload.max_fps,
        is_enabled=payload.is_enabled
    )
    db.add(skill)
    _audit(db, user.username, "SKILL_REGISTERED", f"Registered AI skill {payload.skill_id} ({payload.name})")
    db.commit()
    db.refresh(skill)
    return {"status": "success", "skill_id": skill.skill_id, "id": skill.id}


@router.put("/skills/{skill_id}")
def update_skill(
    skill_id: str,
    payload: SkillUpdateSchema,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Updates an existing AI skill in the registry (RBAC: Admin)."""
    skill = db.query(AISkillRegistry).filter(AISkillRegistry.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    update_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(skill, k, v)

    _audit(db, user.username, "SKILL_UPDATED", f"Updated AI skill {skill_id}: {list(update_data.keys())}")
    db.commit()
    return {"status": "success", "skill_id": skill_id}


@router.delete("/skills/{skill_id}")
def delete_skill(
    skill_id: str,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Deletes an AI skill and unassigns it from all cameras (RBAC: Admin)."""
    skill = db.query(AISkillRegistry).filter(AISkillRegistry.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")

    # Remove assignments
    db.query(CameraSkillAssignment).filter(CameraSkillAssignment.skill_id == skill_id).delete()
    db.delete(skill)
    _audit(db, user.username, "SKILL_DELETED", f"Deleted AI skill {skill_id}")
    db.commit()
    return {"status": "success", "deleted_skill_id": skill_id}


@router.post("/skills/assign")
def assign_skill_to_camera(
    payload: SkillAssignmentSchema,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Assigns an AI skill to a specific camera (RBAC: Admin)."""
    skill = db.query(AISkillRegistry).filter(AISkillRegistry.skill_id == payload.skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{payload.skill_id}' not found in registry.")

    assignment = (
        db.query(CameraSkillAssignment)
        .filter(
            CameraSkillAssignment.camera_id == payload.camera_id,
            CameraSkillAssignment.skill_id == payload.skill_id
        )
        .first()
    )
    if not assignment:
        assignment = CameraSkillAssignment(
            camera_id=payload.camera_id,
            skill_id=payload.skill_id,
            config_json=payload.config_json or "{}"
        )
        db.add(assignment)
    else:
        assignment.config_json = payload.config_json or "{}"

    _audit(db, user.username, "SKILL_ASSIGNED", f"Assigned {payload.skill_id} to {payload.camera_id}")
    db.commit()
    return {"status": "success", "camera_id": payload.camera_id, "skill_id": payload.skill_id}


@router.get("/skills/assignments")
def list_skill_assignments(
    camera_id: Optional[str] = Query(default=None),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Lists camera skill assignments (RBAC: Viewer+)."""
    q = db.query(CameraSkillAssignment)
    if camera_id:
        q = q.filter(CameraSkillAssignment.camera_id == camera_id)
    items = q.all()
    return {
        "total": len(items),
        "items": [
            {
                "id": a.id,
                "camera_id": a.camera_id,
                "skill_id": a.skill_id,
                "config": json.loads(a.config_json or "{}")
            }
            for a in items
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Event Rules Endpoints (/event-rules)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/event-rules")
def list_event_rules(
    is_active: Optional[bool] = Query(default=None),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Lists all declarative multi-condition event rules (RBAC: Viewer+)."""
    q = db.query(EventRule)
    if is_active is not None:
        q = q.filter(EventRule.is_active == is_active)
    rules = q.order_by(EventRule.id.asc()).all()
    return {
        "total": len(rules),
        "items": [
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "name": r.name,
                "severity": r.severity,
                "cooldown_seconds": r.cooldown_seconds,
                "is_active": r.is_active,
                "conditions": json.loads(r.conditions_json or "[]"),
                "actions": json.loads(r.actions_json or "[]")
            }
            for r in rules
        ]
    }


@router.post("/event-rules", status_code=status.HTTP_201_CREATED)
def create_event_rule(
    payload: EventRuleCreateSchema,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Creates a new declarative event rule (RBAC: Admin)."""
    existing = db.query(EventRule).filter(EventRule.rule_id == payload.rule_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Rule '{payload.rule_id}' already exists.")

    rule = EventRule(
        rule_id=payload.rule_id,
        name=payload.name,
        conditions_json=payload.conditions_json or "[]",
        actions_json=payload.actions_json or "[]",
        severity=payload.severity,
        cooldown_seconds=payload.cooldown_seconds,
        is_active=payload.is_active
    )
    db.add(rule)
    _audit(db, user.username, "RULE_CREATED", f"Created event rule {payload.rule_id} ({payload.name})")
    db.commit()
    db.refresh(rule)
    return {"status": "success", "rule_id": rule.rule_id, "id": rule.id}


@router.put("/event-rules/{rule_id}")
def update_event_rule(
    rule_id: str,
    payload: EventRuleUpdateSchema,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Updates an existing declarative event rule (RBAC: Admin)."""
    rule = db.query(EventRule).filter(EventRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")

    update_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(rule, k, v)

    _audit(db, user.username, "RULE_UPDATED", f"Updated event rule {rule_id}: {list(update_data.keys())}")
    db.commit()
    return {"status": "success", "rule_id": rule_id}


@router.delete("/event-rules/{rule_id}")
def delete_event_rule(
    rule_id: str,
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """Deletes an event rule (RBAC: Admin)."""
    rule = db.query(EventRule).filter(EventRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")

    db.delete(rule)
    _audit(db, user.username, "RULE_DELETED", f"Deleted event rule {rule_id}")
    db.commit()
    return {"status": "success", "deleted_rule_id": rule_id}
