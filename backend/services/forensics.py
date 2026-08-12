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
from .event_export import compute_sha256, _parse_segment_timestamp
from ..utils.audit import log_audit_event
from ..utils.security import safe_join_path

router = APIRouter(prefix="/forensics", tags=["Forensics"])

EXPORT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "exports"))
RECORDINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))

from ..utils.timezone import IST_TZ, get_ist_now, get_ist_now_iso

_EXPORTS_LEDGER = []

def _to_naive_ist(dt: datetime.datetime | None) -> datetime.datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(IST_TZ).replace(tzinfo=None)
    return dt

def _parse_forensic_time(ts_str):
    if not ts_str:
        return None
    try:
        if ts_str.endswith("Z"):
            clean = ts_str[:-1] + "+00:00"
        else:
            clean = ts_str
        dt = datetime.datetime.fromisoformat(clean)
        if dt.tzinfo is not None:
            return dt.astimezone(IST_TZ).replace(tzinfo=None)
        return dt
    except Exception:
        return None

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
        
        ts_ist = _to_naive_ist(log.timestamp)
        ts_str = ts_ist.strftime("%H:%M:%S IST") if ts_ist else (log.timestamp.isoformat() if log.timestamp else "N/A")

        result.append({
            "export_uuid": str(log.id),
            "camera_name": cam_name,
            "username": log.username or "operator",
            "role": "operator",
            "timestamp": ts_str,
            "start_time": start_t,
            "end_time": end_t,
            "sha256_hash": sha,
            "timestamp_authority": "VMS Server Internal (NTP-synced IST / Asia/Kolkata)",
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

@router.get("/available-range")
def get_camera_recording_range(camera_id: str = Query(...), db: Session = Depends(get_db)):
    """Returns the start and end timestamp of available recording footage for a camera in IST."""
    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    if not os.path.exists(cam_rec_dir) and os.path.exists(RECORDINGS_DIR):
        for item in os.listdir(RECORDINGS_DIR):
            if item.lower() == camera_id.lower():
                cam_rec_dir = os.path.join(RECORDINGS_DIR, item)
                break

    if not os.path.exists(cam_rec_dir):
        return {
            "camera_id": camera_id,
            "available": False,
            "start_time": None,
            "end_time": None,
            "total_segments": 0,
            "message": "No recording directory found for this camera."
        }

    all_files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
    valid_files = [
        os.path.join(cam_rec_dir, f) for f in all_files 
        if os.path.exists(os.path.join(cam_rec_dir, f)) and os.path.getsize(os.path.join(cam_rec_dir, f)) >= 100000
    ]

    if not valid_files:
        return {
            "camera_id": camera_id,
            "available": False,
            "start_time": None,
            "end_time": None,
            "total_segments": 0,
            "message": "No valid recording segments available for this camera."
        }

    timestamps = []
    for fpath in valid_files:
        dt = _to_naive_ist(_parse_segment_timestamp(os.path.basename(fpath)))
        if dt:
            timestamps.append(dt)

    if not timestamps:
        return {
            "camera_id": camera_id,
            "available": False,
            "start_time": None,
            "end_time": None,
            "total_segments": 0,
            "message": "Recording segments exist but timestamps could not be parsed."
        }

    timestamps.sort()
    earliest_dt = timestamps[0]
    latest_dt = timestamps[-1] + datetime.timedelta(seconds=60.0)

    fmt = "%Y-%m-%d %H:%M:%S"
    return {
        "camera_id": camera_id,
        "available": True,
        "start_time": earliest_dt.strftime(fmt),
        "end_time": latest_dt.strftime(fmt),
        "total_segments": len(valid_files),
        "message": f"Recording available from {earliest_dt.strftime(fmt)} to {latest_dt.strftime(fmt)} (IST)"
    }


@router.get("/available-ranges")
def get_all_camera_recording_ranges(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """Returns available recording start and end timestamps for all registered cameras in IST."""
    cameras = db.query(Camera).all()
    results = []
    
    fmt = "%Y-%m-%d %H:%M:%S"
    fmt_iso = "%Y-%m-%d %H:%M:%S"

    for cam in cameras:
        cam_rec_dir = os.path.join(RECORDINGS_DIR, cam.id)
        if not os.path.exists(cam_rec_dir):
            results.append({
                "camera_id": cam.id,
                "camera_name": cam.name,
                "available": False,
                "start_time": None,
                "end_time": None,
                "total_segments": 0,
                "message": "No recording directory found."
            })
            continue

        all_files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
        valid_files = [
            os.path.join(cam_rec_dir, f) for f in all_files 
            if os.path.exists(os.path.join(cam_rec_dir, f)) and os.path.getsize(os.path.join(cam_rec_dir, f)) >= 100000
        ]

        if not valid_files:
            results.append({
                "camera_id": cam.id,
                "camera_name": cam.name,
                "available": False,
                "start_time": None,
                "end_time": None,
                "total_segments": 0,
                "message": "No valid recording segments available."
            })
            continue

        timestamps = []
        for fpath in valid_files:
            dt = _to_naive_ist(_parse_segment_timestamp(os.path.basename(fpath)))
            if dt:
                timestamps.append(dt)

        if not timestamps:
            results.append({
                "camera_id": cam.id,
                "camera_name": cam.name,
                "available": False,
                "start_time": None,
                "end_time": None,
                "total_segments": 0,
                "message": "Recording segments exist but timestamps unparseable."
            })
            continue

        timestamps.sort()
        earliest_dt = timestamps[0]
        latest_dt = timestamps[-1] + datetime.timedelta(seconds=60.0)

        results.append({
            "camera_id": cam.id,
            "camera_name": cam.name,
            "available": True,
            "start_time": earliest_dt.strftime(fmt),
            "end_time": latest_dt.strftime(fmt),
            "start_time_iso": earliest_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time_iso": latest_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_segments": len(valid_files),
            "message": f"Recording available from {earliest_dt.strftime(fmt)} to {latest_dt.strftime(fmt)} (IST)"
        })

    return results


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
    import logging
    logger = logging.getLogger(__name__)
    t_start = get_ist_now()

    logger.info(f"[ForensicsExport] Starting evidence export in IST for Camera '{camera_id}' (duration={duration_seconds}s, user={user.username})...")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    cam_name = cam.name if cam else camera_id
    
    dt_start = _parse_forensic_time(start_time)
    dt_end = _parse_forensic_time(end_time)

    if dt_start and dt_end:
        if dt_end <= dt_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Validation Error: End time must be strictly after Start time."
            )
        now_ist = get_ist_now().replace(tzinfo=None)
        if dt_start > now_ist:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Validation Error: Start time cannot be in the future."
            )
        calculated_duration = max(1, int((dt_end - dt_start).total_seconds()))
    else:
        calculated_duration = duration_seconds

    logger.info(f"[ForensicsExport] Step 1/4: Locating recording files for '{cam_name}' (IST start={start_time}, end={end_time})...")
    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    if not os.path.exists(cam_rec_dir) and os.path.exists(RECORDINGS_DIR):
        for item in os.listdir(RECORDINGS_DIR):
            if item.lower() == camera_id.lower():
                cam_rec_dir = os.path.join(RECORDINGS_DIR, item)
                break

    matching_files = []
    
    if os.path.exists(cam_rec_dir):
        all_files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
        now_ts = datetime.datetime.now().timestamp()
        valid_files = []
        for f in all_files:
            fpath = os.path.join(cam_rec_dir, f)
            if os.path.exists(fpath) and os.path.getsize(fpath) >= 100000:
                # Exclude the newest file if modified < 4.0s ago (actively being written by OpenCV, missing moov atom)
                if len(all_files) > 1 and f == all_files[-1] and (now_ts - os.path.getmtime(fpath)) < 4.0:
                    continue
                valid_files.append(fpath)

        if dt_start and dt_end:
            win_start = dt_start
            win_end = dt_end
        else:
            win_end = get_ist_now().replace(tzinfo=None)
            win_start = win_end - datetime.timedelta(seconds=calculated_duration)

        # Match files that overlap [win_start, win_end] in IST
        segment_matches = []
        for fpath in valid_files:
            fname = os.path.basename(fpath)
            seg_start = _to_naive_ist(_parse_segment_timestamp(fname))
            if seg_start:
                seg_end = seg_start + datetime.timedelta(seconds=60.0)  # assume 60s per file segment
                if seg_start <= win_end and seg_end >= win_start:
                    segment_matches.append((seg_start, fpath))

        segment_matches.sort(key=lambda x: x[0])
        matching_files = [f for _, f in segment_matches]

        # FALLBACK: If no exact segment overlaps window (e.g. requested time falls in a recording gap or past recording),
        # locate nearest segment for this camera.
        if not matching_files and valid_files:
            target_t = dt_start or win_start
            best_fpath = None
            min_diff = float("inf")
            for fpath in valid_files:
                fname = os.path.basename(fpath)
                seg_start = _to_naive_ist(_parse_segment_timestamp(fname))
                if seg_start:
                    diff = abs((seg_start - target_t).total_seconds())
                    if diff < min_diff:
                        min_diff = diff
                        best_fpath = fpath

            if best_fpath:
                matching_files = [best_fpath]
                logger.info(f"[ForensicsExport] Selected nearest available segment '{os.path.basename(best_fpath)}' for '{cam_name}'.")

    if not matching_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RECORDING NOT AVAILABLE: No recorded footage exists for Camera '{cam_name}' within or near the requested time range ({start_time or 'N/A'} to {end_time or 'N/A'})."
        )

    logger.info(f"[ForensicsExport] Step 1/4 OK: Selected {len(matching_files)} target segment file(s) for {calculated_duration}s clip.")
    export_id = str(uuid.uuid4())[:8]
    zip_filename = f"evidence_{camera_id}_{export_id}.zip"
    zip_path = os.path.join(EXPORT_DIR, zip_filename)
    
    temp_dir = os.path.join(EXPORT_DIR, f"temp_{export_id}")
    os.makedirs(temp_dir, exist_ok=True)
    clip_out_path = os.path.join(temp_dir, "clip.mp4")

    try:
        if matching_files:
            # Calculate offset inside first matched file
            f0_start = _to_naive_ist(_parse_segment_timestamp(os.path.basename(matching_files[0])))
            if f0_start and dt_start:
                start_offset = max(0.0, (dt_start - f0_start).total_seconds())
                if start_offset >= 60.0:
                    start_offset = 0.0
            else:
                start_offset = 0.0

            logger.info(f"[ForensicsExport] Step 2/4: Extracting {calculated_duration}s clip (start_offset={start_offset:.2f}s, files={len(matching_files)})...")
            need_reencode = redact_faces or redact_plates

            if not need_reencode and len(matching_files) == 1:
                # Fast Lossless Stream Copy (< 50ms)
                cmd_copy = [
                    "ffmpeg", "-y", "-ss", f"{start_offset:.3f}", "-i", matching_files[0],
                    "-t", str(calculated_duration),
                    "-c", "copy", "-avoid_negative_ts", "make_zero",
                    "-movflags", "+faststart", clip_out_path
                ]
                res = subprocess.run(cmd_copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                if res.returncode != 0 or not os.path.exists(clip_out_path) or os.path.getsize(clip_out_path) < 500:
                    logger.warning(f"[ForensicsExport] Stream copy failed (rc={res.returncode}, err={res.stderr.decode('utf-8', 'ignore')[:200]}), attempting reencode...")
                    need_reencode = True

            if need_reencode and len(matching_files) == 1:
                cmd = [
                    "ffmpeg", "-y", "-ss", f"{start_offset:.3f}", "-i", matching_files[0],
                    "-t", str(calculated_duration),
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", clip_out_path
                ]
                res_re = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                if res_re.returncode != 0:
                    logger.error(f"[ForensicsExport] Re-encode failed (rc={res_re.returncode}, err={res_re.stderr.decode('utf-8', 'ignore')[:300]})")
            elif len(matching_files) > 1:
                concat_txt = os.path.join(temp_dir, "concat.txt")
                with open(concat_txt, "w") as f:
                    for mf in matching_files:
                        safe_p = mf.replace("\\", "/")
                        f.write(f"file '{safe_p}'\n")
                
                c_mode = ["-c:v", "libx264", "-preset", "ultrafast"] if need_reencode else ["-c", "copy", "-avoid_negative_ts", "make_zero"]
                cmd = [
                    "ffmpeg", "-y", "-ss", f"{start_offset:.3f}", "-f", "concat", "-safe", "0", "-i", concat_txt,
                    "-t", str(calculated_duration)
                ] + c_mode + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", clip_out_path]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)

        if not os.path.exists(clip_out_path) or os.path.getsize(clip_out_path) == 0:
            logger.error(f"[ForensicsExport] FFmpeg extraction failed for {matching_files}. ffmpeg_copy_rc={res.returncode if 'res' in locals() else 'N/A'}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"RECORDING EXTRACTION FAILED: Could not slice video stream for Camera '{cam_name}'."
            )

        logger.info(f"[ForensicsExport] Step 3/4: Computing SHA-256 digital signature...")
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

        logger.info(f"[ForensicsExport] Step 4/4: Archiving ZIP package '{zip_filename}'...")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    compress_type = zipfile.ZIP_STORED if file.endswith((".mp4", ".avi", ".mkv")) else zipfile.ZIP_DEFLATED
                    zipf.write(full_p, file, compress_type=compress_type)
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

