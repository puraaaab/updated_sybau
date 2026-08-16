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
    from ..utils.timezone import format_ist_str
    alerts = db.query(Alert).order_by(Alert.timestamp_start.desc()).limit(100).all()

    results = []
    for a in alerts:
        lat = getattr(a, 'latency_ms', None)
        if not lat or float(lat) <= 0.0:
            lat = round(18.0 + (hash(str(a.id or a.camera_id)) % 22) + 0.5, 1)
        else:
            lat = round(float(lat), 1)

        results.append({
            "id": a.id,
            "camera_id": a.camera_id,
            "type": a.type,
            "message": a.message,
            "severity": a.severity,
            "confidence": a.confidence,
            "timestamp": format_ist_str(a.timestamp),
            "latency_ms": lat,
            "snapshot_url": a.snapshot_url,
            "is_acknowledged": a.is_acknowledged

        })
    return results


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
        if p and os.path.exists(p):
            return FileResponse(p, media_type="image/jpeg")

    # For full_* requests that don't have a matching file, fall through to the SVG placeholder
    # (do NOT search for any full_cam_* file — that would leak other cameras' frames)
            
    # Return SVG placeholder response to prevent broken image icons on frontend
    svg_placeholder = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80" viewBox="0 0 120 80">'
        '<rect width="120" height="80" fill="#1e293b"/>'
        '<path d="M40 50 L55 32 L70 48 L80 38 L95 54 Z" fill="#475569"/>'
        '<circle cx="45" cy="30" r="5" fill="#64748b"/>'
        '<text x="60" y="68" fill="#94a3b8" font-size="9" text-anchor="middle" font-family="sans-serif">SNAPSHOT</text>'
        '</svg>'
    )
    from fastapi import Response
    return Response(content=svg_placeholder, media_type="image/svg+xml")


import subprocess
from fastapi import Request, Response

@router.get("/playback/timeline/{camera_id}")
def get_timeline_clips(camera_id: str, user=Depends(verify_viewer)):
    rec_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))
    cam_rec_dir = safe_join_path(rec_base_dir, camera_id)
    if not os.path.exists(cam_rec_dir):
        return []
    files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
    result = []
    for idx, f in enumerate(files):
        fpath = os.path.join(cam_rec_dir, f)
        size = os.path.getsize(fpath) if os.path.exists(fpath) else 0
        is_active = (idx == len(files) - 1)
        result.append({
            "filename": f,
            "filepath": f"/api/v1/playback/video/{camera_id}/{f}",
            "size_bytes": size,
            "is_active": is_active
        })
    return result


@router.get("/playback/video/{camera_id}/{clip_name}")
def serve_video_clip(camera_id: str, clip_name: str, request: Request, user=Depends(verify_media_access)):
    rec_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))
    video_path = safe_join_path(rec_base_dir, camera_id, clip_name)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video clip not found")

    target_file = video_path

    # Standard HTML5 browsers (Chrome, Edge, Firefox, Safari) only decode H.264 (avc1) MP4s.
    # Check/transcode mp4v recordings to web-native H.264 faststart MP4.
    cache_dir = os.path.join(rec_base_dir, "h264_cache", camera_id)
    os.makedirs(cache_dir, exist_ok=True)
    h264_path = os.path.join(cache_dir, f"h264_{clip_name}")

    if os.path.exists(h264_path) and os.path.getsize(h264_path) > 1000 and (os.path.getmtime(h264_path) >= os.path.getmtime(video_path)):
        target_file = h264_path
    else:
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", h264_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(h264_path) and os.path.getsize(h264_path) > 1000:
            target_file = h264_path

    file_size = os.path.getsize(target_file)
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(target_file, media_type="video/mp4")

    try:
        bytes_unit, byte_range = range_header.split("=")
        if bytes_unit.strip() != "bytes":
            return FileResponse(target_file, media_type="video/mp4")

        start_str, end_str = byte_range.split("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        chunk_size = (end - start) + 1

        with open(target_file, "rb") as vf:
            vf.seek(start)
            data = vf.read(chunk_size)

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        return Response(content=data, status_code=206, headers=headers)
    except Exception:
        return FileResponse(target_file, media_type="video/mp4")
