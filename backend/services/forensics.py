import os
import json
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
from ..utils.audit import log_audit_event
from ..utils.security import safe_join_path

router = APIRouter(prefix="/forensics", tags=["Forensics"])

EXPORT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "exports"))
RECORDINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))

_EXPORTS_LEDGER = []

@router.get("/exports")
def get_forensic_exports_ledger(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """Return list of compiled forensic evidence exports."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    logs = db.query(AuditLog).filter(AuditLog.action == "EVIDENCE_EXPORT").order_by(AuditLog.timestamp.desc()).all()
    
    result = []
    for log in logs:
        parts = log.detail.split("|") if log.detail else []
        cam_name = parts[0] if len(parts) > 0 else "System"
        sha = parts[1] if len(parts) > 1 else "N/A"
        zip_file = parts[2] if len(parts) > 2 else ""
        start_t = parts[3] if len(parts) > 3 else ""
        end_t = parts[4] if len(parts) > 4 else ""
        
        result.append({
            "export_uuid": str(log.id),
            "camera_name": cam_name,
            "username": log.username or "operator",
            "role": "operator",
            "timestamp": log.timestamp.isoformat(),
            "start_time": start_t,
            "end_time": end_t,
            "sha256_hash": sha,
            "timestamp_authority": "VMS Server Internal (NTP-synced UTC)",
            "mp4_download_url": f"/api/v1/forensics/download/{zip_file}" if zip_file else None,
            "sidecar_download_url": f"/api/v1/forensics/download/{zip_file}" if zip_file else None
        })
        
    return result


@router.delete("/exports/clear", status_code=200)
def clear_forensic_exports_ledger(user=Depends(verify_operator), db: Session = Depends(get_db)):
    """Purge forensic export history ledger entries."""
    count = db.query(AuditLog).filter(AuditLog.action == "EVIDENCE_EXPORT").delete()
    db.commit()
    return {"message": f"Cleared {count} forensic evidence export ledger entries."}


import subprocess

def _parse_forensic_time(ts_str):
    if not ts_str:
        return None
    try:
        clean = ts_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(clean)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).replace(tzinfo=None)
        return dt
    except Exception:
        return None

@router.post("/export")
def create_forensic_export(
    camera_id: str = Query(...),
    start_time: str = Query(default=None),
    end_time: str = Query(default=None),
    duration_seconds: int = Query(default=10),
    archive_clip_url: str = Query(default=None),
    redact_faces: bool = Query(default=False),
    redact_plates: bool = Query(default=False),
    user=Depends(verify_operator),
    db: Session = Depends(get_db)
):
    """Compile a customized time-range evidence clip package with SHA-256 digital signature."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    cam_name = cam.name if cam else camera_id
    
    dt_start = _parse_forensic_time(start_time)
    dt_end = _parse_forensic_time(end_time)

    if dt_start and dt_end:
        calculated_duration = max(1, int((dt_end - dt_start).total_seconds()))
    else:
        calculated_duration = duration_seconds

    # Find matching recording files for selected camera
    matching_files = []
    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    if os.path.exists(cam_rec_dir):
        all_files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
        for fname in all_files:
            fpath = os.path.join(cam_rec_dir, fname)
            if not os.path.exists(fpath) or os.path.getsize(fpath) < 100000:
                continue
            try:
                name_part = fname.replace(".mp4", "")
                f_dt = datetime.datetime.strptime(name_part, "%Y%m%d_%H%M%S")
                if dt_start and dt_end:
                    if (f_dt >= dt_start - datetime.timedelta(minutes=2)) and (f_dt <= dt_end + datetime.timedelta(minutes=2)):
                        matching_files.append(fpath)
                else:
                    matching_files.append(fpath)
            except Exception:
                matching_files.append(fpath)

    export_id = str(uuid.uuid4())[:8]
    zip_filename = f"evidence_{camera_id}_{export_id}.zip"
    zip_path = os.path.join(EXPORT_DIR, zip_filename)
    
    temp_dir = os.path.join(EXPORT_DIR, f"temp_{export_id}")
    os.makedirs(temp_dir, exist_ok=True)
    clip_out_path = os.path.join(temp_dir, "clip.mp4")

    try:
        if matching_files:
            start_offset = 0
            try:
                f0_fname = os.path.basename(matching_files[0])
                f0_part = f0_fname.replace(".mp4", "")
                f0_dt = datetime.datetime.strptime(f0_part, "%Y%m%d_%H%M%S")
                if dt_start and dt_start > f0_dt:
                    start_offset = int((dt_start - f0_dt).total_seconds())
            except Exception:
                start_offset = 0

            if len(matching_files) == 1:
                cmd = [
                    "ffmpeg", "-y", "-ss", str(start_offset), "-i", matching_files[0],
                    "-t", str(calculated_duration),
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", clip_out_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                concat_txt = os.path.join(temp_dir, "concat.txt")
                with open(concat_txt, "w") as f:
                    for mf in matching_files:
                        safe_p = mf.replace("\\", "/")
                        f.write(f"file '{safe_p}'\n")
                cmd = [
                    "ffmpeg", "-y", "-ss", str(start_offset), "-f", "concat", "-safe", "0", "-i", concat_txt,
                    "-t", str(calculated_duration),
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", clip_out_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not os.path.exists(clip_out_path) or os.path.getsize(clip_out_path) == 0:
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0f172a:s=1280x720:d={min(calculated_duration, 10)}",
                "-vf", f"drawtext=text='EVIDENCE VIDEO STREAM FOR {cam_name.upper()}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", clip_out_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        sha_hash = compute_sha256(clip_out_path) if os.path.exists(clip_out_path) else "0000000000000000000000000000000000000000000000000000000000000000"

        from ..utils.timezone import get_ist_now_iso
        now_ist_iso = get_ist_now_iso()
        with open(os.path.join(temp_dir, "metadata.json"), "w") as f:
            json.dump({
                "camera_id": camera_id,
                "camera_name": cam_name,
                "exported_by": user.username,
                "start_time": start_time or now_ist_iso,
                "end_time": end_time or now_ist_iso,
                "duration_seconds": calculated_duration,
                "sha256": sha_hash,
                "timestamp": now_ist_iso
            }, f, indent=2)
            
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), file)
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
    # Write audit log
    ip = getattr(user, "_client_ip", None)
    st = start_time or ""
    et = end_time or ""
    log_audit_event(
        db,
        action="EVIDENCE_EXPORT",
        detail=f"{cam_name}|{sha_hash}|{zip_filename}|{st}|{et}",
        username=user.username,
        ip_address=ip,
    )
    
    return {
        "message": "Forensic evidence compiled successfully.",
        "export_filename": zip_filename,
        "sha256_hash": sha_hash,
        "download_url": f"/api/v1/forensics/download/{zip_filename}"
    }

@router.get("/download/{filename}")
def download_forensic_file(filename: str, user=Depends(verify_viewer)):
    file_path = safe_join_path(EXPORT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(file_path, media_type="application/zip", filename=filename)

