from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Face, Vehicle, SceneCaption, GlobalIdentity
from ..auth.helpers import verify_viewer
from ..ai.captioning.captioner import get_florence_queue_stats

router = APIRouter(tags=["Ledger Records"])


@router.get("/records/stats")
def get_records_stats(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    faces_count = db.query(Face).count()
    vehicles_count = db.query(Vehicle).count()
    plates_count = db.query(Vehicle).filter(Vehicle.license_plate.isnot(None)).count()
    captions_count = db.query(SceneCaption).count()
    identities_count = db.query(GlobalIdentity).count()
    return {
        "faces_count": faces_count,
        "vehicles_count": vehicles_count,
        "plates_count": plates_count,
        "captions_count": captions_count,
        "identities_count": identities_count
    }


def _resolve_vehicle_snapshot(v) -> str | None:
    if getattr(v, "snapshot_url", None):
        return v.snapshot_url
    if v.license_plate:
        import uuid
        clean_p = str(v.license_plate).strip().upper().replace(" ", "")
        vid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"VEHICLE_{clean_p}"))
        return f"/api/v1/playback/snapshot/{vid}"
    if v.track_uuid:
        return f"/api/v1/playback/snapshot/{v.track_uuid}"
    return None


@router.get("/records/faces")
def get_records_faces(
    limit: int = Query(default=50, le=50000),
    offset: int = Query(default=0),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    q = db.query(Face)
    if search:
        q = q.filter(Face.label.ilike(f"%{search}%") | Face.track_uuid.ilike(f"%{search}%"))
    total = q.count()
    order_clause = Face.id.desc() if sort.lower() == "desc" else Face.id.asc()
    if limit > 0:
        items = q.order_by(order_clause).offset(offset).limit(limit).all()
    else:
        items = q.order_by(order_clause).offset(offset).all()
    results = []
    for f in items:
        results.append({
            "id": f.id,
            "track_uuid": f.track_uuid,
            "label": f.label or "Unidentified Subject",
            "confidence": round(f.confidence, 2) if f.confidence else 0.85,
            "timestamp": f.timestamp.strftime("%Y-%m-%d %H:%M:%S") if f.timestamp else None,
            "snapshot_url": f"/api/v1/playback/snapshot/{f.embedding_id}" if f.embedding_id else None
        })
    return {"total": total, "items": results}


@router.get("/records/vehicles")
def get_records_vehicles(
    limit: int = Query(default=50, le=50000),
    offset: int = Query(default=0),
    camera_id: str = Query(default=None),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    q = db.query(Vehicle)
    if camera_id:
        q = q.filter(Vehicle.camera_id == camera_id)
    if search:
        q = q.filter(
            (Vehicle.vehicle_type.ilike(f"%{search}%")) |
            (Vehicle.vehicle_color.ilike(f"%{search}%")) |
            (Vehicle.license_plate.ilike(f"%{search}%")) |
            (Vehicle.track_uuid.ilike(f"%{search}%"))
        )
    total = q.count()
    order_clause = Vehicle.id.desc() if sort.lower() == "desc" else Vehicle.id.asc()
    if limit > 0:
        items = q.order_by(order_clause).offset(offset).limit(limit).all()
    else:
        items = q.order_by(order_clause).offset(offset).all()
    results = []
    for v in items:
        results.append({
            "id": v.id,
            "camera_id": v.camera_id,
            "track_uuid": v.track_uuid,
            "license_plate": v.license_plate,
            "vehicle_type": v.vehicle_type or "car",
            "vehicle_color": v.vehicle_color or "unknown",
            "ocr_confidence": round(v.ocr_confidence, 2) if v.ocr_confidence else 0.0,
            "snapshot_url": _resolve_vehicle_snapshot(v),
            "timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else None
        })
    return {"total": total, "items": results}


@router.get("/records/plates")
def get_records_plates(
    limit: int = Query(default=50, le=50000),
    offset: int = Query(default=0),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    q = db.query(Vehicle).filter(Vehicle.license_plate.isnot(None))
    if search:
        q = q.filter(Vehicle.license_plate.ilike(f"%{search}%"))
    total = q.count()
    order_clause = Vehicle.id.desc() if sort.lower() == "desc" else Vehicle.id.asc()
    if limit > 0:
        items = q.order_by(order_clause).offset(offset).limit(limit).all()
    else:
        items = q.order_by(order_clause).offset(offset).all()
    results = []
    for v in items:
        results.append({
            "id": v.id,
            "camera_id": v.camera_id,
            "track_uuid": v.track_uuid,
            "license_plate": v.license_plate,
            "vehicle_type": v.vehicle_type,
            "ocr_confidence": round(v.ocr_confidence, 2) if v.ocr_confidence else 0.90,
            "snapshot_url": _resolve_vehicle_snapshot(v),
            "timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else None
        })
    return {"total": total, "items": results}


@router.get("/records/captions")
def get_records_captions(
    limit: int = Query(default=50, le=50000),
    offset: int = Query(default=0),
    camera_id: str = Query(default=None),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    q = db.query(SceneCaption)
    if camera_id:
        q = q.filter(SceneCaption.camera_id == camera_id)
    if search:
        q = q.filter(SceneCaption.caption.ilike(f"%{search}%"))
    total = q.count()
    order_clause = SceneCaption.id.desc() if sort.lower() == "desc" else SceneCaption.id.asc()
    if limit > 0:
        items = q.order_by(order_clause).offset(offset).limit(limit).all()
    else:
        items = q.order_by(order_clause).offset(offset).all()
    results = []
    for c in items:
        results.append({
            "id": c.id,
            "camera_id": c.camera_id,
            "caption": c.caption,
            "snapshot_url": c.snapshot_url,
            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S") if c.timestamp else None
        })
    return {"total": total, "items": results}


@router.get("/florence/stats")
def get_florence_stats():
    try:
        return get_florence_queue_stats()
    except Exception:
        return {"captioning": 0, "queue": 0}
