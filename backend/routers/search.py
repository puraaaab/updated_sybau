import os
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Camera, Vehicle
from ..auth.helpers import verify_viewer
from ..search import vector_search
from ..ai.model_manager import model_manager
from ..config.service import get_models
from ..ai.face import face_pipeline

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/semantic")
def search_semantic(
    q: str = Query(..., min_length=1), 
    limit: int = Query(default=10),
    start_time: str = Query(default=None),
    end_time: str = Query(default=None),
    user=Depends(verify_viewer)
):
    results = vector_search.perform_semantic_search(q, limit=limit, start_time=start_time, end_time=end_time)
    return results


@router.get("/license-plate")
def search_license_plate(
    q: str = Query(..., min_length=1), 
    limit: int = Query(default=50), 
    db: Session = Depends(get_db), 
    user=Depends(verify_viewer)
):
    search_query = f"%{q.strip().upper()}%"
    results = db.query(Vehicle).filter(
        Vehicle.license_plate.like(search_query)
    ).order_by(
        Vehicle.timestamp.desc()
    ).limit(limit).all()
    
    camera_map = {cam.id: cam.name for cam in db.query(Camera).all()}
    
    return [
        {
            "id": vehicle.id,
            "license_plate": vehicle.license_plate,
            "ocr_confidence": vehicle.ocr_confidence,
            "vehicle_type": vehicle.vehicle_type,
            "timestamp": vehicle.timestamp,
            "track_uuid": vehicle.track_uuid,
            "camera_id": vehicle.camera_id or "Unknown",
            "camera_name": camera_map.get(vehicle.camera_id, "Unknown") if vehicle.camera_id else "Unknown"
        } for vehicle in results
    ]


@router.get("/debug")
def debug_search(user=Depends(verify_viewer)):
    cfg = get_models()
    snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "snapshots"))
    return {
        "vector_db_len": len(model_manager.vector_db),
        "demo_mode": cfg.get("demo_mode", False),
        "module_id": id(model_manager),
        "qdrant_status": "ONLINE",
        "snapshots_dir_count": len(os.listdir(snap_dir)) if os.path.exists(snap_dir) else 0
    }


@router.post("/face")
async def search_face(
    file: UploadFile = File(...), 
    start_time: str = Query(default=None),
    end_time: str = Query(default=None),
    user=Depends(verify_viewer)
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode image format. Upload a valid JPG/PNG file.")

    h, w = img.shape[:2]
    try:
        detector, recognizer = face_pipeline.get_face_models(w, h)
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)

        if faces is not None and len(faces) > 0:
            aligned_face = recognizer.alignCrop(img, faces[0])
            embedding = recognizer.feature(aligned_face).flatten().tolist()
            results = vector_search.perform_face_search(embedding, start_time=start_time, end_time=end_time)
            return results
        else:
            raise HTTPException(status_code=422, detail="No face detected in uploaded image. Please provide a clear face snapshot.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Face embedding pipeline error: {str(e)}")
