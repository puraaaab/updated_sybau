from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..auth.helpers import verify_admin, verify_viewer
from ..config import service as config_service
from ..utils.audit import log_audit_event

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("")
def get_settings(user=Depends(verify_viewer)):
    return {
        "alerts": config_service.get_alerts(),
        "models": config_service.get_models()
    }


@router.post("/alerts")
def save_alerts_settings(settings: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    config_service.save_alerts(settings)
    ip = getattr(user, "_client_ip", None)
    log_audit_event(db, action="SETTINGS_UPDATE", detail="Updated alert thresholds", username=user.username, ip_address=ip)
    return {"message": "Alert thresholds updated"}


@router.post("/models")
def save_models_settings(settings: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    config_service.save_models(settings)
    ip = getattr(user, "_client_ip", None)
    log_audit_event(db, action="SETTINGS_UPDATE", detail="Updated model configurations", username=user.username, ip_address=ip)
    return {"message": "Model settings updated"}
