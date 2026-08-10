from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Face, Vehicle, SceneCaption, GlobalIdentity, RawOCR
from ..auth.helpers import verify_viewer
from ..ai.captioning.captioner import get_florence_queue_stats
from ..utils.timezone import format_ist_str

router = APIRouter(tags=["Ledger Records"])


@router.get("/records/stats")
def get_records_stats(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    faces_count = db.query(Face).count()
    vehicles_count = db.query(Vehicle).count()
    plates_count = db.query(Vehicle).filter(
        Vehicle.license_plate.isnot(None),
        ~Vehicle.license_plate.startswith("VEHICLE_"),
        ~Vehicle.license_plate.startswith("POI_")
    ).count()
    ocr_count = db.query(RawOCR).count()
    captions_count = db.query(SceneCaption).count()
    identities_count = db.query(GlobalIdentity).count()
    return {
        "faces_count": faces_count,
        "vehicles_count": vehicles_count,
        "plates_count": plates_count,
        "ocr_count": ocr_count,
        "captions_count": captions_count,
        "identities_count": identities_count
    }


def _resolve_vehicle_snapshot(v) -> str | None:
    if getattr(v, "snapshot_url", None):
        return v.snapshot_url
    lp = str(v.license_plate or "").strip()
    if lp and not lp.startswith("VEHICLE_") and not lp.startswith("POI_"):
        import uuid
        clean_p = lp.upper().replace(" ", "")
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
    try:
        db.query(Face).filter(Face.label.startswith("VEHICLE_")).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()

    from sqlalchemy import func
    from ..database.models import Track

    # Group by face label to collapse duplicate sightings of the same POI subject
    subq = (
        db.query(
            Face.label.label("poi_label"),
            func.max(Face.id).label("max_id"),
            func.count(Face.id).label("sightings")
        )
        .filter(~Face.label.startswith("VEHICLE_"))
        .group_by(Face.label)
    )

    if search:
        subq = subq.filter(Face.label.ilike(f"%{search}%") | Face.track_uuid.ilike(f"%{search}%"))

    subq_aliased = subq.subquery()
    total = db.query(func.count(subq_aliased.c.poi_label)).scalar() or 0

    order_clause = subq_aliased.c.max_id.desc() if sort.lower() == "desc" else subq_aliased.c.max_id.asc()
    query = (
        db.query(Face, subq_aliased.c.sightings)
        .join(subq_aliased, Face.id == subq_aliased.c.max_id)
        .order_by(order_clause)
    )

    if limit > 0:
        query = query.offset(offset).limit(limit)
    else:
        query = query.offset(offset)

    items = query.all()
    results = []
    for f, sightings_count in items:
        cam_rows = (
            db.query(Track.camera_id)
            .join(Face, Track.track_uuid == Face.track_uuid)
            .filter(Face.label == f.label)
            .distinct().all()
        )
        cams = [r[0] for r in cam_rows if r[0]]
        cam_summary = ", ".join(sorted(set(cams))) if cams else "Live Grid"

        results.append({
            "id": f.id,
            "track_uuid": f.track_uuid,
            "label": f.label or "Unidentified Subject",
            "confidence": round(f.confidence, 2) if f.confidence else 0.85,
            "sightings": sightings_count,
            "cameras": cam_summary,
            "timestamp": format_ist_str(f.timestamp),
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
            "license_plate": v.license_plate if (v.license_plate and not v.license_plate.startswith("VEHICLE_") and not v.license_plate.startswith("POI_")) else None,
            "vehicle_type": v.vehicle_type or "car",
            "vehicle_color": v.vehicle_color or "unknown",
            "ocr_confidence": round(v.ocr_confidence, 2) if v.ocr_confidence else 0.0,
            "snapshot_url": _resolve_vehicle_snapshot(v),
            "timestamp": format_ist_str(v.timestamp)
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
    q = db.query(Vehicle).filter(
        Vehicle.license_plate.isnot(None),
        ~Vehicle.license_plate.startswith("VEHICLE_"),
        ~Vehicle.license_plate.startswith("POI_")
    )
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
            "timestamp": format_ist_str(v.timestamp)
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
            "timestamp": format_ist_str(c.timestamp)
        })
    return {"total": total, "items": results}


@router.get("/records/ocr")
def get_records_ocr(
    limit: int = Query(default=50, le=50000),
    offset: int = Query(default=0),
    camera_id: str = Query(default=None),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    q = db.query(RawOCR)
    if camera_id:
        q = q.filter(RawOCR.camera_id == camera_id)
    if search:
        q = q.filter(
            (RawOCR.detected_text.ilike(f"%{search}%")) |
            (RawOCR.raw_text.ilike(f"%{search}%")) |
            (RawOCR.track_uuid.ilike(f"%{search}%"))
        )
    total = q.count()
    order_clause = RawOCR.id.desc() if sort.lower() == "desc" else RawOCR.id.asc()
    if limit > 0:
        items = q.order_by(order_clause).offset(offset).limit(limit).all()
    else:
        items = q.order_by(order_clause).offset(offset).all()
    results = []
    for r in items:
        results.append({
            "id": r.id,
            "camera_id": r.camera_id,
            "track_uuid": r.track_uuid,
            "detected_text": r.detected_text,
            "raw_text": r.raw_text or r.detected_text,
            "ocr_confidence": round(r.ocr_confidence, 2) if r.ocr_confidence else 0.0,
            "source_type": r.source_type or "license_plate",
            "snapshot_url": r.snapshot_url,
            "timestamp": format_ist_str(r.timestamp)
        })
    return {"total": total, "items": results}


@router.get("/florence/stats")
def get_florence_stats():
    try:
        return get_florence_queue_stats()
    except Exception:
        return {"captioning": 0, "queue": 0}
