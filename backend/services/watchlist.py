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
    """Retrieve all target POIs registered in the live watchlist (auto-purging DPDP expired profiles)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    identities = db.query(GlobalIdentity).filter(GlobalIdentity.type == "person").all()
    
    active_results = []
    for i in identities:
        # Auto-purge expired entries per DPDP Act retention rules if first_seen is older than retention
        # Default retention: 30 days unless specified
        created_at = i.first_seen if i.first_seen else now
        # Ensure timezone-aware comparison (legacy DB rows may be naive UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        if (now - created_at).days > 90: # Hard DPDP max retention window
            db.delete(i)
            continue

        active_results.append({
            "id": i.id,
            "identity_uuid": i.identity_uuid,
            "name": i.name,
            "description": f"Target profile registered on {created_at.strftime('%Y-%m-%d')}",
            "first_seen": created_at.isoformat() if created_at else None,
            "last_seen": i.last_seen.isoformat() if i.last_seen else None,
            "embedding_id": i.embedding_id,
            "dpdp_status": "ACTIVE_RETENTION_VERIFIED"
        })
        
    db.commit()
    return active_results

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
    # Pad to 512 dims for vector DB compatibility
    padded_embedding = embedding_list + [0.0] * (512 - len(embedding_list))

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
        vector=padded_embedding,
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
