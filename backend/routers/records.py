from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Face, Vehicle, SceneCaption, GlobalIdentity, RawOCR, Camera
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
    camera_id: str = Query(default=None),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    camera_id_val = camera_id if isinstance(camera_id, str) else None
    search_val = search if isinstance(search, str) else None
    sort_val = sort if isinstance(sort, str) else "desc"

    q = db.query(Face)
    if camera_id_val:
        q = q.filter(Face.camera_id == camera_id_val)
    if search_val:
        q = q.filter(
            (Face.label.ilike(f"%{search_val}%")) |
            (Face.track_uuid.ilike(f"%{search_val}%"))
        )
    total = q.count()
    order_clause = Face.id.desc() if sort_val.lower() == "desc" else Face.id.asc()
    if limit_val > 0:
        items = q.order_by(order_clause).offset(offset_val).limit(limit_val).all()
    else:
        items = q.order_by(order_clause).offset(offset_val).all()

    camera_map = {cam.id: cam.name for cam in db.query(Camera).all()}
    results = []
    for f in items:
        snap_id = f.embedding_id or f.track_uuid
        results.append({
            "id": f.id,
            "track_uuid": f.track_uuid,
            "camera_id": f.camera_id,
            "cameras": camera_map.get(f.camera_id, f.camera_id or "Live Grid"),
            "label": f.label or "Unidentified Subject",
            "confidence": round(f.confidence, 2) if getattr(f, "confidence", None) else 0.85,
            "sightings": 1,
            "timestamp": format_ist_str(f.timestamp),
            "snapshot_url": f"/api/v1/playback/snapshot/{snap_id}" if snap_id else None
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
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    camera_id_val = camera_id if isinstance(camera_id, str) else None
    search_val = search if isinstance(search, str) else None
    sort_val = sort if isinstance(sort, str) else "desc"

    q = db.query(Vehicle)
    if camera_id_val:
        q = q.filter(Vehicle.camera_id == camera_id_val)
    if search_val:
        q = q.filter(
            (Vehicle.vehicle_type.ilike(f"%{search_val}%")) |
            (Vehicle.vehicle_color.ilike(f"%{search_val}%")) |
            (Vehicle.license_plate.ilike(f"%{search_val}%")) |
            (Vehicle.track_uuid.ilike(f"%{search_val}%"))
        )
    total = q.count()
    order_clause = Vehicle.id.desc() if sort_val.lower() == "desc" else Vehicle.id.asc()
    if limit_val > 0:
        items = q.order_by(order_clause).offset(offset_val).limit(limit_val).all()
    else:
        items = q.order_by(order_clause).offset(offset_val).all()
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
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    search_val = search if isinstance(search, str) else None
    sort_val = sort if isinstance(sort, str) else "desc"

    q = db.query(Vehicle).filter(
        Vehicle.license_plate.isnot(None),
        ~Vehicle.license_plate.startswith("VEHICLE_"),
        ~Vehicle.license_plate.startswith("POI_")
    )
    if search_val:
        q = q.filter(Vehicle.license_plate.ilike(f"%{search_val}%"))
    total = q.count()
    order_clause = Vehicle.id.desc() if sort_val.lower() == "desc" else Vehicle.id.asc()
    if limit_val > 0:
        items = q.order_by(order_clause).offset(offset_val).limit(limit_val).all()
    else:
        items = q.order_by(order_clause).offset(offset_val).all()
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
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    camera_id_val = camera_id if isinstance(camera_id, str) else None
    search_val = search if isinstance(search, str) else None
    sort_val = sort if isinstance(sort, str) else "desc"

    q = db.query(SceneCaption)
    if camera_id_val:
        q = q.filter(SceneCaption.camera_id == camera_id_val)
    if search_val:
        q = q.filter(SceneCaption.caption.ilike(f"%{search_val}%"))
    total = q.count()
    order_clause = SceneCaption.id.desc() if sort_val.lower() == "desc" else SceneCaption.id.asc()
    if limit_val > 0:
        items = q.order_by(order_clause).offset(offset_val).limit(limit_val).all()
    else:
        items = q.order_by(order_clause).offset(offset_val).all()
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
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    camera_id_val = camera_id if isinstance(camera_id, str) else None
    search_val = search if isinstance(search, str) else None
    sort_val = sort if isinstance(sort, str) else "desc"

    q = db.query(RawOCR)
    if camera_id_val:
        q = q.filter(RawOCR.camera_id == camera_id_val)
    if search_val:
        q = q.filter(
            (RawOCR.detected_text.ilike(f"%{search_val}%")) |
            (RawOCR.raw_text.ilike(f"%{search_val}%")) |
            (RawOCR.track_uuid.ilike(f"%{search_val}%"))
        )
    total = q.count()
    order_clause = RawOCR.id.desc() if sort_val.lower() == "desc" else RawOCR.id.asc()
    if limit_val > 0:
        items = q.order_by(order_clause).offset(offset_val).limit(limit_val).all()
    else:
        items = q.order_by(order_clause).offset(offset_val).all()
    results = []
    for o in items:
        results.append({
            "id": o.id,
            "camera_id": o.camera_id,
            "track_uuid": o.track_uuid,
            "detected_text": o.detected_text,
            "raw_text": o.raw_text,
            "ocr_confidence": round(o.ocr_confidence, 2) if o.ocr_confidence else 0.85,
            "source_type": o.source_type,
            "snapshot_url": o.snapshot_url,
            "timestamp": format_ist_str(o.timestamp)
        })
    return {"total": total, "items": results}


@router.get("/florence/stats")
def get_florence_stats(user=Depends(verify_viewer)):
    try:
        from ..ai.captioning.captioner import get_florence_queue_stats
        from ..ai.captioning.moondream_captioner import get_moondream_stats
        from ..config.service import get_models

        f_stats = get_florence_queue_stats()
        md_stats = get_moondream_stats()

        merged_cam_stats = dict(f_stats.get("camera_stats", {}))
        for cid, md_cam in md_stats.get("camera_stats", {}).items():
            if cid not in merged_cam_stats or md_cam.get("last_caption"):
                merged_cam_stats[cid] = md_cam

        moondream_enabled = get_models().get("moondream", {}).get("enabled", True)
        active_model = md_stats.get("model", "moondream3.1-9B-A2B") if moondream_enabled else "microsoft/Florence-2-base"

        return {
            "captioning": f_stats.get("captioning", 0) + md_stats.get("in_flight", 0),
            "queue": f_stats.get("queue", 0) + md_stats.get("queue", 0),
            "captioned": f_stats.get("captioned", 0) + md_stats.get("captioned", 0),
            "active_cameras": f_stats.get("active_cameras", list(merged_cam_stats.keys())),
            "camera_stats": merged_cam_stats,
            "rotation_cursor": f_stats.get("rotation_cursor", 0),
            "moondream_active": moondream_enabled,
            "model": active_model
        }
    except Exception:
        return {"captioning": 0, "queue": 0, "captioned": 0, "camera_stats": {}}
