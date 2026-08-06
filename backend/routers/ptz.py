import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Camera
from ..auth.helpers import verify_operator
from ..services.onvif_ptz import send_ptz_command
from ..services.ptz_tracker import toggle_auto_tracking

router = APIRouter(prefix="/cameras", tags=["PTZ Control"])


@router.post("/{camera_id}/ptz/control")
async def control_ptz(camera_id: str, payload: dict, user=Depends(verify_operator), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    action = payload.get("action", "ContinuousMove")
    pan = float(payload.get("pan", 0.0))
    tilt = float(payload.get("tilt", 0.0))
    zoom = float(payload.get("zoom", 0.0))

    parsed = urllib.parse.urlparse(cam.stream_url if cam.stream_url.startswith("http") or cam.stream_url.startswith("rtsp") else "http://127.0.0.1")
    ip = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80

    res = await send_ptz_command(ip, port, action, pan, tilt, zoom)
    return {"camera_id": camera_id, "ptz_result": res}


@router.post("/{camera_id}/ptz/auto-track")
def set_ptz_auto_track(camera_id: str, payload: dict, user=Depends(verify_operator)):
    enabled = payload.get("enabled", False)
    target_id = payload.get("target_id", None)
    res = toggle_auto_tracking(camera_id, enabled, target_id)
    return res
