from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import CustomAlertRule
from ..auth.helpers import verify_operator, verify_viewer
from ..ai.behavior.custom_rules import clear_rule_cache

router = APIRouter(prefix="/rules", tags=["Custom Alert Rules"])


@router.get("")
def get_custom_rules(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    rules = db.query(CustomAlertRule).order_by(CustomAlertRule.id.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "prompt": r.prompt,
            "camera_id": r.camera_id,
            "severity": r.severity,
            "is_active": r.is_active,
            "confidence_threshold": r.confidence_threshold,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in rules
    ]


@router.post("")
def create_custom_rule(payload: dict, user=Depends(verify_operator), db: Session = Depends(get_db)):
    prompt = (payload.get("prompt") or payload.get("name") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Rule prompt cannot be empty.")

    rule = CustomAlertRule(
        name=payload.get("name") or prompt,
        prompt=prompt,
        camera_id=payload.get("camera_id", "ALL"),
        severity=payload.get("severity", "high"),
        is_active=True,
        confidence_threshold=float(payload.get("confidence_threshold", 0.65))
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    clear_rule_cache()

    return {
        "id": rule.id,
        "name": rule.name,
        "prompt": rule.prompt,
        "camera_id": rule.camera_id,
        "severity": rule.severity,
        "is_active": rule.is_active,
        "confidence_threshold": rule.confidence_threshold
    }


@router.put("/{rule_id}/toggle")
def toggle_custom_rule(rule_id: int, user=Depends(verify_operator), db: Session = Depends(get_db)):
    rule = db.query(CustomAlertRule).filter(CustomAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.is_active = not rule.is_active
    db.commit()
    clear_rule_cache()
    return {"id": rule.id, "is_active": rule.is_active}


@router.delete("/{rule_id}")
def delete_custom_rule(rule_id: int, user=Depends(verify_operator), db: Session = Depends(get_db)):
    rule = db.query(CustomAlertRule).filter(CustomAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(rule)
    db.commit()
    clear_rule_cache()
    return {"message": "Rule deleted"}
