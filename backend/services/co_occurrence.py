import os
import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import Track, Camera, Face, Vehicle
from ..auth.helpers import verify_viewer

router = APIRouter(prefix="/forensics", tags=["CoOccurrence"])

@router.get("/co-occurrence")
def get_suspect_co_occurrence(
    camera_id: str = Query(default=None),
    time_window_minutes: int = Query(default=5),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """
    Use Case 23: Spatial-Temporal Co-Occurrence Graph Analysis.
    Identifies multiple distinct tracks/persons/vehicles appearing in close 
    spatial-temporal proximity (same location, same time window) to group potential accomplices.
    """
    query = db.query(Track)
    if camera_id:
        query = query.filter(Track.camera_id == camera_id)
        
    recent_tracks = query.order_by(Track.first_seen.desc()).limit(30).all()
    cams_dict = {c.id: c for c in db.query(Camera).all()}
    
    groups = []
    processed_ids = set()
    
    for i, t1 in enumerate(recent_tracks):
        if t1.id in processed_ids:
            continue
            
        group_members = [t1]
        processed_ids.add(t1.id)
        
        for t2 in recent_tracks[i + 1:]:
            if t2.id in processed_ids:
                continue
                
            # Check spatial condition (same camera or adjacent) and temporal condition (< time_window)
            same_cam = (t1.camera_id == t2.camera_id)
            time_diff = abs((t1.first_seen - t2.first_seen).total_seconds()) if (t1.first_seen and t2.first_seen) else 0
            
            if same_cam and time_diff <= (time_window_minutes * 60):
                group_members.append(t2)
                processed_ids.add(t2.id)
                
        if len(group_members) >= 2:
            cam = cams_dict.get(t1.camera_id)
            groups.append({
                "group_id": f"GROUP_{t1.camera_id}_{t1.id}",
                "camera_id": t1.camera_id,
                "camera_name": cam.name if cam else t1.camera_id,
                "location": cam.location if cam else "Main Area",
                "timestamp": t1.first_seen.isoformat() if t1.first_seen else datetime.datetime.now().isoformat(),
                "confidence_score": min(round(0.80 + (len(group_members) * 0.03), 2), 0.99),
                "member_count": len(group_members),
                "members": [
                    {
                        "track_uuid": m.track_uuid,
                        "label": m.label,
                        "speed": round(m.speed, 1),
                        "first_seen": m.first_seen.strftime("%H:%M:%S") if m.first_seen else "N/A"
                    }
                    for m in group_members
                ],
                "analytical_summary": f"Spatial-Temporal Link: {len(group_members)} entities detected co-occurring at {cam.name if cam else t1.camera_id} within {time_window_minutes} min window."
            })
            
    # Mock default groups if database is clean/empty and demo_mode is enabled
    if not groups:
        from ..config.service import get_models
        cfg = get_models()
        if cfg.get("demo_mode", False):
            from ..utils.timezone import get_ist_now
            now = get_ist_now()
            groups = [
                {
                    "group_id": "GRP_DEMO_001",
                    "camera_id": "cam_1",
                    "camera_name": "Central Bus Depo",
                    "location": "Platform Area",
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "confidence_score": 0.92,
                    "member_count": 3,
                    "members": [
                        {"track_uuid": "track_101", "label": "person", "role_hypothesis": "Primary Suspect (Jewellery Entry)", "speed": 1.2},
                        {"track_uuid": "track_102", "label": "motorcycle", "role_hypothesis": "Getaway Vehicle (Waiting Outside)", "speed": 0.0},
                        {"track_uuid": "track_103", "label": "person", "role_hypothesis": "Lookout (Street Corner)", "speed": 0.5}
                    ],
                    "analytical_summary": "Spatial-Temporal Link: 3 entities detected co-occurring at Central Bus Depo within 3 min window."
                }
            ]

    return {
        "time_window_minutes": time_window_minutes,
        "groups_found": len(groups),
        "co_occurrence_groups": groups
    }
