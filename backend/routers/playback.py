import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Alert
from ..auth.helpers import verify_operator, verify_viewer, verify_media_access
from ..services import event_export
from ..utils.security import safe_join_path

router = APIRouter(tags=["Playback & Alerts"])


@router.get("/alerts")
def get_alerts_history(db: Session = Depends(get_db), user=Depends(verify_viewer)):
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).limit(100).all()
    return alerts


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), user=Depends(verify_operator)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_acknowledged = True
    db.commit()
    return {"message": "Alert acknowledged"}


@router.get("/alerts/{alert_id}/export")
def download_forensic_export(alert_id: int, db: Session = Depends(get_db), user=Depends(verify_operator)):
    try:
        zip_path = event_export.export_alert_evidence(alert_id, db)
        return FileResponse(zip_path, media_type="application/zip", filename=os.path.basename(zip_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/playback/snapshot/{snap_id}")
def serve_snapshot(snap_id: str, user=Depends(verify_media_access)):
    snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
    
    candidates = [
        safe_join_path(snap_dir, f"{snap_id}.jpg"),
        safe_join_path(snap_dir, snap_id),
    ]
    if not snap_id.endswith(".jpg"):
        candidates.append(safe_join_path(snap_dir, f"{snap_id}.png"))
        
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="image/jpeg")
            
    raise HTTPException(status_code=404, detail="Snapshot not found")


@router.get("/playback/timeline/{camera_id}")
def get_timeline_clips(camera_id: str, user=Depends(verify_viewer)):
    rec_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))
    cam_rec_dir = safe_join_path(rec_base_dir, camera_id)
    if not os.path.exists(cam_rec_dir):
        return []
    files = sorted(os.listdir(cam_rec_dir))
    return [{"filename": f, "filepath": f"/api/v1/playback/video/{camera_id}/{f}"} for f in files if f.endswith(".mp4")]


@router.get("/playback/video/{camera_id}/{clip_name}")
def serve_video_clip(camera_id: str, clip_name: str, user=Depends(verify_media_access)):
    rec_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))
    video_path = safe_join_path(rec_base_dir, camera_id, clip_name)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video clip not found")
    return FileResponse(video_path, media_type="video/mp4")
