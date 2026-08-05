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

@router.get("")
def get_watchlist(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """
    Retrieve all target POIs registered in the live watchlist.
    COMP-02 FIX: GET endpoint no longer deletes records (was a REST violation).
    DPDP retention purge is now a separate admin-only action endpoint.
    """
    _UTC = datetime.timezone.utc
    now = datetime.datetime.now(_UTC)
    identities = db.query(GlobalIdentity).filter(GlobalIdentity.type == "person").all()

    active_results = []
    for i in identities:
        created_at = i.first_seen if i.first_seen else now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=_UTC)

        days_held = (now - created_at).days
        # Flag entries approaching DPDP 90-day limit but do NOT delete on GET
        dpdp_status = "ACTIVE_RETENTION_VERIFIED"
        if days_held > 90:
            dpdp_status = "RETENTION_EXCEEDED_PURGE_REQUIRED"
        elif days_held > 75:
            dpdp_status = "APPROACHING_RETENTION_LIMIT"

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
    _UTC = datetime.timezone.utc
    now = datetime.datetime.now(_UTC)
    identities = db.query(GlobalIdentity).filter(GlobalIdentity.type == "person").all()

    purged = []
    for i in identities:
        created_at = i.first_seen if i.first_seen else now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=_UTC)
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

    now = datetime.datetime.now(datetime.timezone.utc)
    new_poi = GlobalIdentity(
        identity_uuid=identity_uuid,
        type="person",
        name=name,
        first_seen=now,
        last_seen=now,
        embedding_id=short_uuid
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
        "description": description
    }

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
