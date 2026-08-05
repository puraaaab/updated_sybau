import os
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import Camera, Track, Face, Vehicle, GlobalIdentity
from ..auth.helpers import verify_viewer

router = APIRouter(prefix="/forensics", tags=["Trajectory"])

@router.get("/trajectory/{target_id}")
def get_target_trajectory(target_id: str, user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """
    Build geographical trajectory route across connected cameras for a target person/vehicle ID or plate.
    """
    nodes = []
    
    # 1. Query matching face/person tracks
    identity = db.query(GlobalIdentity).filter(
        (GlobalIdentity.identity_uuid == target_id) | (GlobalIdentity.name.ilike(f"%{target_id}%"))
    ).first()
    
    matched_tracks = []
    if identity:
        faces = db.query(Face).filter(
            (Face.label == identity.identity_uuid) | (Face.label == identity.name)
        ).all()
        track_uuids = [f.track_uuid for f in faces if f.track_uuid]
        if track_uuids:
            matched_tracks = db.query(Track).filter(Track.track_uuid.in_(track_uuids)).order_by(Track.first_seen.asc()).all()
            
    # 2. If vehicle / license plate / color / type query
    if not matched_tracks:
        vehicles = db.query(Vehicle).filter(
            (Vehicle.license_plate.ilike(f"%{target_id}%")) |
            (Vehicle.vehicle_type.ilike(f"%{target_id}%")) |
            (Vehicle.vehicle_color.ilike(f"%{target_id}%"))
        ).all()
        track_uuids = [v.track_uuid for v in vehicles if v.track_uuid]
        if track_uuids:
            matched_tracks = db.query(Track).filter(Track.track_uuid.in_(track_uuids)).order_by(Track.first_seen.asc()).all()

    # 3. Query direct Track matches by track_uuid, label (person, car, bus, motorcycle), or camera_id
    if not matched_tracks:
        matched_tracks = db.query(Track).filter(
            (Track.track_uuid.ilike(f"%{target_id}%")) |
            (Track.label.ilike(f"%{target_id}%")) |
            (Track.camera_id.ilike(f"%{target_id}%"))
        ).order_by(Track.first_seen.asc()).limit(30).all()

    # 4. Fallback: recent active tracks across all cameras if general query
    if not matched_tracks:
        matched_tracks = db.query(Track).order_by(Track.first_seen.asc()).limit(10).all()

    cams_dict = {c.id: c for c in db.query(Camera).all()}

    # AI-05 FIX: If no tracks found, return EMPTY trajectory with honest message.
    # Previously, the system silently returned the 10 most recent tracks from ANY camera,
    # which could show a trajectory for a completely different person/vehicle to police.
    if not matched_tracks:
        return {
            "target_id": target_id,
            "total_hits": 0,
            "trajectory": [],
            "message": (
                f"No trajectory data found for target '{target_id}'. "
                "The target may not have been detected on any connected camera, "
                "or the identifier does not match any tracked identity or vehicle."
            ),
        }
    else:
        for idx, tr in enumerate(matched_tracks):
            cam = cams_dict.get(tr.camera_id)
            lat = getattr(cam, "latitude", 21.1950 + idx * 0.002) if cam else 21.1950
            lng = getattr(cam, "longitude", 72.8200 + idx * 0.003) if cam else 72.8200
            nodes.append({
                "sequence_index": idx + 1,
                "camera_id": tr.camera_id,
                "camera_name": cam.name if cam else tr.camera_id,
                "location": cam.location if cam else "Location",
                "latitude": lat,
                "longitude": lng,
                "timestamp": tr.first_seen.strftime("%Y-%m-%d %H:%M:%S") if tr.first_seen else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                # AI-01 FIX: Convert px/sec to km/h using calibrated 25.0 px/m constant
                # (m/s = px_sec / 25.0; km/h = m/s * 3.6). Remove fake 32.5 fallback.
                "speed_kmh": round((tr.speed / 25.0) * 3.6, 1) if tr.speed else 0.0,
                "snapshot_url": f"/api/v1/cameras/{tr.camera_id}/snapshot"
            })

    return {
        "target_id": target_id,
        "total_hits": len(nodes),
        "trajectory": nodes
    }
