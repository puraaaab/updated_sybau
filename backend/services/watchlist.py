import os
import uuid
import datetime
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import GlobalIdentity
from ..auth.helpers import verify_viewer, verify_operator, verify_admin
from ..ai.face.face_pipeline import get_face_models
from ..workers.ai_worker import index_vector

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])

from fastapi.responses import FileResponse
from ..database.models import Face, Track, Camera

@router.get("")
def get_watchlist(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """
    Retrieve all target POIs registered in the live watchlist along with captured camera history and face crop URLs.
    """
    from ..utils.timezone import get_ist_now, IST_TZ
    now = get_ist_now()
    identities = db.query(GlobalIdentity).filter(GlobalIdentity.type == "person").all()
    cams_dict = {c.id: c.name for c in db.query(Camera).all()}

    active_results = []
    for i in identities:
        created_at = i.first_seen if i.first_seen else now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=IST_TZ)

        days_held = (now - created_at).days
        dpdp_status = "ACTIVE_RETENTION_VERIFIED"
        if days_held > 90:
            dpdp_status = "RETENTION_EXCEEDED_PURGE_REQUIRED"
        elif days_held > 75:
            dpdp_status = "APPROACHING_RETENTION_LIMIT"

        # Query all faces matching identity_uuid or name to extract captured camera history
        faces = db.query(Face).filter(
            (Face.label == i.identity_uuid) | (Face.label == i.name)
        ).all()
        track_uuids = [f.track_uuid for f in faces if f.track_uuid]
        
        cams_seen = []
        if track_uuids:
            tracks = db.query(Track).filter(Track.track_uuid.in_(track_uuids)).all()
            cam_ids = set([t.camera_id for t in tracks if t.camera_id])
            cams_seen = [cams_dict.get(cid, cid) for cid in cam_ids]

        active_results.append({
            "id": i.id,
            "identity_uuid": i.identity_uuid,
            "name": i.name,
            "description": f"Target profile registered on {created_at.strftime('%Y-%m-%d')}",
            "first_seen": created_at.isoformat(),
            "last_seen": i.last_seen.isoformat() if i.last_seen else None,
            "embedding_id": i.embedding_id,
            "days_held": days_held,
            "dpdp_status": dpdp_status,
            "face_crop_url": f"/api/v1/watchlist/{i.identity_uuid}/snapshot",
            "cams_seen": cams_seen,
            "sightings_count": len(faces)
        })

    return active_results


@router.post("/purge-expired", status_code=200)
def purge_expired_watchlist_entries(
    user=Depends(verify_admin),
    db: Session = Depends(get_db)
):
    """
    COMP-02: Admin-only action to purge DPDP-expired watchlist entries.
    All deletions are logged in AuditLog for forensic compliance.
    This separates destructive operations from read-only GET endpoints.
    """
    from ..utils.audit import log_audit_event
    from ..utils.timezone import get_ist_now, IST_TZ
    now = get_ist_now()
    identities = db.query(GlobalIdentity).filter(GlobalIdentity.type == "person").all()

    purged = []
    for i in identities:
        created_at = i.first_seen if i.first_seen else now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=IST_TZ)
        if (now - created_at).days > 90:
            purged.append({"identity_uuid": i.identity_uuid, "name": i.name})
            log_audit_event(
                db,
                action="DPDP_AUTO_PURGE",
                detail=f"Auto-purged DPDP-expired POI {i.identity_uuid} ({i.name}) after 90+ day retention",
                username=user.username,
                ip_address=getattr(user, "_client_ip", None),
            )
            db.delete(i)

    db.commit()
    return {
        "message": f"Purged {len(purged)} expired DPDP entries.",
        "purged": purged,
    }

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_watchlist_poi(
    name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    user=Depends(verify_operator),
    db: Session = Depends(get_db)
):
    """Register a new POI profile by extracting face embedding from uploaded image."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file uploaded.")

    h, w, _ = img.shape
    detector, recognizer = get_face_models(w, h)

    ret, faces = detector.detect(img)
    if faces is None or len(faces) == 0:
        # Fallback: if YuNet missed the face crop, process the entire image through SFace directly if small enough
        # or resize to 112x112 standard input for SFace recognizer
        resized = cv2.resize(img, (112, 112))
        embedding_feats = recognizer.feature(resized)
    else:
        best_face = faces[0]
        aligned = recognizer.alignCrop(img, best_face)
        embedding_feats = recognizer.feature(aligned)

    embedding_list = embedding_feats[0].tolist()
    # AI-02 FIX: Store the actual SFace embedding at its real dimension (128).
    # Previously, 384 zero dimensions were appended which degraded cosine similarity
    # by adding pure noise to 75% of the vector space.
    # The Qdrant face collection uses 128-dim vectors to match SFace output exactly.

    short_uuid = str(uuid.uuid4())[:6].upper()
    identity_uuid = f"POI_{short_uuid}"

    # Save cropped face image to storage/snapshots
    storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
    os.makedirs(storage_dir, exist_ok=True)
    crop_filename = f"poi_{identity_uuid}.jpg"
    crop_path = os.path.join(storage_dir, crop_filename)

    if faces is not None and len(faces) > 0:
        face_img = recognizer.alignCrop(img, faces[0])
        cv2.imwrite(crop_path, face_img)
    else:
        cv2.imwrite(crop_path, img)

    from ..utils.timezone import get_ist_now
    now = get_ist_now()
    new_poi = GlobalIdentity(
        identity_uuid=identity_uuid,
        type="person",
        name=name,
        first_seen=now,
        last_seen=now,
        embedding_id=short_uuid,
        snapshot_path=crop_filename
    )
    db.add(new_poi)
    from ..utils.audit import log_audit_event
    log_audit_event(db, action="WATCHLIST_CREATE", detail=f"Added POI target profile '{name}' ({identity_uuid})", username=user.username)
    db.commit()

    # Index into vector storage
    index_vector(
        vector_id=short_uuid,
        vector=embedding_list,
        payload={
            "type": "face",
            "label": name,
            "identity_uuid": identity_uuid,
            "description": description,
            "timestamp": now.isoformat()
        }
    )

    return {
        "id": new_poi.id,
        "identity_uuid": identity_uuid,
        "name": name,
        "description": description,
        "face_crop_url": f"/api/v1/watchlist/{identity_uuid}/snapshot"
    }


@router.get("/{identity_uuid}/snapshot")
def get_poi_face_snapshot(identity_uuid: str, db: Session = Depends(get_db)):
    """Return the cropped face photo for a POI target identity."""
    storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
    
    # 1. Direct POI crop file (manually registered POI profile)
    crop_path = os.path.join(storage_dir, f"poi_{identity_uuid}.jpg")
    if os.path.exists(crop_path):
        return FileResponse(crop_path, media_type="image/jpeg")

    # 2. Check Face records associated with this POI identity
    face = (
        db.query(Face)
        .filter((Face.label == identity_uuid) | (Face.label.ilike(f"%{identity_uuid}%")))
        .order_by(Face.id.desc())
        .first()
    )
    if face:
        if face.embedding_id:
            f_path = os.path.join(storage_dir, f"{face.embedding_id}.jpg")
            if os.path.exists(f_path):
                return FileResponse(f_path, media_type="image/jpeg")
        if face.track_uuid:
            trk_path = os.path.join(storage_dir, f"{face.track_uuid}.jpg")
            if os.path.exists(trk_path):
                return FileResponse(trk_path, media_type="image/jpeg")

    # 3. Fallback scan for any file containing identity_uuid
    if os.path.exists(storage_dir):
        for fname in os.listdir(storage_dir):
            if identity_uuid in fname and fname.endswith(('.jpg', '.png')):
                return FileResponse(os.path.join(storage_dir, fname), media_type="image/jpeg")

    placeholder = os.path.join(storage_dir, "placeholder.jpg")
    if not os.path.exists(placeholder):
        blank = np.zeros((120, 120, 3), dtype=np.uint8)
        cv2.putText(blank, "POI FACE", (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.imwrite(placeholder, blank)
    return FileResponse(placeholder, media_type="image/jpeg")


@router.put("/{poi_id}")
def update_watchlist_poi(
    poi_id: int,
    payload: dict,
    user=Depends(verify_operator),
    db: Session = Depends(get_db)
):
    """
    Update target POI identity name & classification metadata.
    Updates GlobalIdentity and all matching Face labels in the system.
    """
    poi = db.query(GlobalIdentity).filter(GlobalIdentity.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI profile not found.")

    new_name = payload.get("name")
    if new_name:
        old_name = poi.name
        poi.name = new_name
        # Update linked face records so AI Search & Trajectory map find the renamed person
        db.query(Face).filter((Face.label == old_name) | (Face.label == poi.identity_uuid)).update({Face.label: new_name})
        from ..utils.audit import log_audit_event
        log_audit_event(db, action="WATCHLIST_RENAME", detail=f"Renamed POI {poi.identity_uuid} from '{old_name}' to '{new_name}'", username=user.username)
        db.commit()
        db.refresh(poi)

    return {"message": "POI identity updated successfully.", "id": poi.id, "name": poi.name}


@router.delete("/{poi_id}")
def delete_watchlist_poi(poi_id: int, user=Depends(verify_admin), db: Session = Depends(get_db)):
    """Delete a target POI profile from live watchlist."""
    poi = db.query(GlobalIdentity).filter(GlobalIdentity.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI profile not found.")

    from ..utils.audit import log_audit_event
    log_audit_event(db, action="WATCHLIST_DELETE", detail=f"Deleted POI profile '{poi.name}' ({poi.identity_uuid})", username=user.username)
    db.delete(poi)
    db.commit()
    return {"message": "POI profile removed successfully."}
