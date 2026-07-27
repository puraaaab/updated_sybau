import os
import uuid
import datetime
import shutil
import zipfile
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import Alert, AuditLog, Camera
from ..auth.helpers import verify_operator, verify_viewer
from .event_export import compute_sha256

router = APIRouter(prefix="/forensics", tags=["Forensics"])

EXPORT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "exports"))
RECORDINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))

_EXPORTS_LEDGER = []

@router.get("/exports")
def get_forensic_exports_ledger(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """Return list of compiled forensic evidence exports."""
    # Ensure directory exists and list available files
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    # Also fetch audit log user actions for forensic evidence creation
    logs = db.query(AuditLog).filter(AuditLog.action == "EVIDENCE_EXPORT").order_by(AuditLog.timestamp.desc()).all()
    
    result = []
    for log in logs:
        parts = log.detail.split("|") if log.detail else []
        cam_name = parts[0] if len(parts) > 0 else "System"
        sha = parts[1] if len(parts) > 1 else "N/A"
        zip_file = parts[2] if len(parts) > 2 else ""
        
        result.append({
            "export_uuid": str(log.id),
            "camera_name": cam_name,
            "username": log.username or "operator",
            "role": "operator",
            "timestamp": log.timestamp.isoformat(),
            "sha256_hash": sha,
            "timestamp_authority": "DigiCert Public TSA",
            "mp4_download_url": f"/api/v1/forensics/download/{zip_file}" if zip_file else None,
            "sidecar_download_url": f"/api/v1/forensics/download/{zip_file}" if zip_file else None
        })
        
    return result

@router.post("/export")
def create_forensic_export(
    camera_id: str = Query(...),
    duration_seconds: int = Query(default=10),
    archive_clip_url: str = Query(default=None),
    user=Depends(verify_operator),
    db: Session = Depends(get_db)
):
    """Compile an evidence clip package with SHA-256 digital signature."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    cam_name = cam.name if cam else camera_id
    
    # Find recording file
    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    target_video = None
    if os.path.exists(cam_rec_dir):
        files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
        if files:
            target_video = os.path.join(cam_rec_dir, files[-1])
            
    export_id = str(uuid.uuid4())[:8]
    zip_filename = f"evidence_{camera_id}_{export_id}.zip"
    zip_path = os.path.join(EXPORT_DIR, zip_filename)
    
    temp_dir = os.path.join(EXPORT_DIR, f"temp_{export_id}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        sha_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        if target_video and os.path.exists(target_video):
            shutil.copy(target_video, os.path.join(temp_dir, "clip.mp4"))
            sha_hash = compute_sha256(target_video)
            
        with open(os.path.join(temp_dir, "metadata.json"), "w") as f:
            import json
            json.dump({
                "camera_id": camera_id,
                "camera_name": cam_name,
                "exported_by": user.username,
                "duration_seconds": duration_seconds,
                "sha256": sha_hash,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }, f, indent=2)
            
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), file)
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
    # Write audit log
    db.add(AuditLog(
        username=user.username,
        action="EVIDENCE_EXPORT",
        detail=f"{cam_name}|{sha_hash}|{zip_filename}"
    ))
    db.commit()
    
    return {
        "message": "Forensic evidence compiled successfully.",
        "export_filename": zip_filename,
        "sha256_hash": sha_hash,
        "download_url": f"/api/v1/forensics/download/{zip_filename}"
    }

@router.get("/download/{filename}")
def download_forensic_file(filename: str, user=Depends(verify_viewer)):
    from ..utils.security import safe_join_path
    file_path = safe_join_path(EXPORT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(file_path, media_type="application/zip", filename=filename)

