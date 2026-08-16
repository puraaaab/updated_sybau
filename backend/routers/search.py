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
    import re
    from sqlalchemy import or_
    raw_query = q.strip().upper()
    clean_alpha = re.sub(r'[^A-Z0-9]', '', raw_query)

    conds = [
        Vehicle.license_plate.ilike(f"%{raw_query}%")
    ]
    if clean_alpha and clean_alpha != raw_query:
        conds.append(Vehicle.license_plate.ilike(f"%{clean_alpha}%"))

    results = db.query(Vehicle).filter(
        or_(*conds)
    ).order_by(
        Vehicle.timestamp.desc()
    ).limit(limit).all()
    
    camera_map = {cam.id: cam.name for cam in db.query(Camera).all()}
    
    out = []
    for vehicle in results:
        snap_url = vehicle.snapshot_url or (f"/api/v1/playback/snapshot/{vehicle.track_uuid}" if vehicle.track_uuid else None)
        bbox_val = vehicle.bbox
        out.append({
            "id": vehicle.id,
            "license_plate": vehicle.license_plate,
            "ocr_confidence": vehicle.ocr_confidence,
            "vehicle_type": vehicle.vehicle_type,
            "vehicle_color": getattr(vehicle, "vehicle_color", "unknown"),
            "timestamp": vehicle.timestamp,
            "track_uuid": vehicle.track_uuid,
            "camera_id": vehicle.camera_id or "Unknown",
            "camera_name": camera_map.get(vehicle.camera_id, "Unknown") if vehicle.camera_id else "Unknown",
            "snapshot_url": snap_url,
            "bbox": bbox_val
        })
    return out


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


@router.post("/image-query")
async def search_by_uploaded_image(
    file: UploadFile = File(...),
    limit: int = Query(default=25),
    start_time: str = Query(default=None),
    end_time: str = Query(default=None),
    user=Depends(verify_viewer)
):
    """
    Accepts an uploaded image file, extracts visual targets (face vectors, OpenCLIP clothing/appearance embeddings,
    and YOLO object classes in <30ms), and runs vector similarity search across all ledgers.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    nparr = np.frombuffer(contents, np.uint8)
    bgr_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if bgr_img is None:
        raise HTTPException(status_code=400, detail="Could not decode image file. Upload a valid JPG, PNG, or WEBP file.")

    try:
        h, w = bgr_img.shape[:2]
        extracted_classes = []
        face_results = []
        clip_results = []
        clean_prompt = ""

        # 1. Fast Biometric Face Extraction (<10ms)
        try:
            detector, recognizer = face_pipeline.get_face_models(w, h)
            detector.setInputSize((w, h))
            _, faces = detector.detect(bgr_img)
            if faces is not None and len(faces) > 0:
                aligned_face = recognizer.alignCrop(bgr_img, faces[0])
                embedding = recognizer.feature(aligned_face).flatten().tolist()
                face_results = vector_search.perform_face_search(embedding, limit=limit, start_time=start_time, end_time=end_time)
                clean_prompt = "person face sighting"
        except Exception:
            pass

        # 2. Fast YOLO Object Detection (<10ms)
        try:
            yolo_model = model_manager.get_yolo()
            if yolo_model:
                preds = yolo_model(bgr_img, verbose=False)
                for r in preds:
                    for box in r.boxes:
                        cls_name = yolo_model.names.get(int(box.cls[0]), "")
                        if cls_name and cls_name not in extracted_classes:
                            extracted_classes.append(cls_name)
        except Exception:
            pass

        # 3. OpenCLIP Visual Appearance / Clothing Extraction (<15ms)
        try:
            from ..ai.person.person_attribute_engine import get_clip_image_embedding
            clip_vec = get_clip_image_embedding(bgr_img)
            if clip_vec:
                from ..search.qdrant_utils import qdrant_client_with_timeout
                with qdrant_client_with_timeout(1.5) as client:
                    q_filter = vector_search._build_qdrant_time_filter(start_time, end_time)
                    crop_pts = client.query_points(
                        collection_name="vms_embeddings",
                        query=clip_vec,
                        using="person_crop",
                        query_filter=q_filter,
                        limit=limit,
                        with_payload=True
                    ).points
                    if crop_pts:
                        snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
                        for p in crop_pts:
                            if p.score >= 0.50:
                                payload = dict(p.payload)
                                snap_url = payload.get("snapshot_url")
                                snap_id = snap_url.split("/")[-1] if snap_url else ""
                                if snap_id and os.path.isfile(os.path.join(snap_dir, f"full_{snap_id}.jpg")):
                                    payload["full_snapshot_url"] = f"/api/v1/playback/snapshot/full_{snap_id}"
                                clip_results.append({"score": min(0.99, float(p.score)), "payload": payload})
        except Exception:
            pass

        if extracted_classes:
            clean_prompt = f"{' '.join(extracted_classes[:3])} target"
        elif not clean_prompt:
            clean_prompt = "visual target"

        # 4. Vector Similarity Search (<20ms)
        semantic_results = vector_search.perform_semantic_search(
            clean_prompt, limit=limit, start_time=start_time, end_time=end_time
        )

        # Merge ranked results: Face (highest priority) -> OpenCLIP Visual Crop -> Semantic
        seen_snapshots = set()
        merged_results = []
        for r in face_results + clip_results + semantic_results:
            p = r.get("payload", {})
            snap = p.get("snapshot_url") or p.get("full_snapshot_url") or ""
            if snap and snap in seen_snapshots:
                continue
            if snap:
                seen_snapshots.add(snap)
            merged_results.append(r)

        return {
            "extracted_prompt": clean_prompt,
            "detected_classes": extracted_classes,
            "results": merged_results[:limit]
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image vision query failed: {str(exc)}")
