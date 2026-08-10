import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Track
from ..auth.helpers import verify_viewer
from ..monitoring import health as monitoring_health
from ..ai.model_manager import model_manager
from ..ai.embeddings.embedder import is_embedder_ready
from ..config.service import get_models
from ..workers.ai_worker import get_latest_telemetry
from ..services.traffic_analytics import compute_traffic_analytics
from ..services.video_qa import answer_video_question

router = APIRouter(tags=["Analytics & Health"])

@router.get("/monitor/health")
def get_health(user=Depends(verify_viewer)):
    return monitoring_health.get_full_health_report()


@router.get("/ai/status")
def get_ai_status(user=Depends(verify_viewer)):
    models = model_manager._models
    yolo_loaded = "yolo" in models
    ocr_loaded = "ocr" in models
    florence_loaded = "florence" in models
    embedder_loaded = is_embedder_ready()

    all_ready = yolo_loaded and embedder_loaded

    import os
    yolo_cfg = get_models().get("yolo", {})
    yolo_model_path = yolo_cfg.get("model_path", "yolo26l.pt")
    yolo_name = os.path.basename(yolo_model_path).replace(".pt", "").upper()

    return {
        "status": "READY" if all_ready else "PREWARMING",
        "all_ready": all_ready,
        "models": {
            yolo_name: "LOADED" if yolo_loaded else "LOADING",
            "OCR": "LOADED" if ocr_loaded else "LOADING",
            "Embedder": "LOADED" if embedder_loaded else "LOADING",
            "Florence": "LOADED" if florence_loaded else "LOADING"
        }
    }


@router.get("/camera-telemetry")
def get_cameras_telemetry(user=Depends(verify_viewer)):
    return get_latest_telemetry()


@router.get("/analytics/heatmap")
def get_spatial_heatmap_data(camera_id: str = Query(default="cam_1"), user=Depends(verify_viewer), db: Session = Depends(get_db)):
    recent_tracks = db.query(Track).filter(Track.camera_id == camera_id).limit(40).all()
    points = []
    
    if recent_tracks:
        for t in recent_tracks:
            px = getattr(t, 'last_bbox_x', 0.5)
            py = getattr(t, 'last_bbox_y', 0.5)
            points.append({
                "x": round(px if px <= 1.0 else px / 1920.0, 3),
                "y": round(py if py <= 1.0 else py / 1080.0, 3),
                "value": round(getattr(t, 'speed', 10.0) / 100.0 if getattr(t, 'speed', 10.0) > 0 else 0.5, 2)
            })
    else:
        cfg = get_models()
        if cfg.get("demo_mode", False):
            hotspots = [
                (0.35, 0.45, 0.9), (0.38, 0.48, 0.85), (0.70, 0.60, 0.95),
                (0.20, 0.30, 0.7), (0.50, 0.50, 0.8), (0.75, 0.65, 0.88),
                (0.85, 0.70, 0.75), (0.15, 0.80, 0.6), (0.40, 0.40, 0.92)
            ]
            for x, y, v in hotspots:
                points.append({"x": x, "y": y, "value": v})
            
    return {
        "camera_id": camera_id,
        "grid_resolution": "high",
        "points_count": len(points),
        "heatmap_points": points
    }


@router.get("/analytics/traffic-speed")
def get_traffic_speed_analytics(camera_id: str = Query(default="cam_1"), user=Depends(verify_viewer), db: Session = Depends(get_db)):
    recent_tracks = db.query(Track).filter(Track.camera_id == camera_id).limit(50).all()
    tracks_payload = []
    for tr in recent_tracks:
        tracks_payload.append({
            "track_uuid": tr.track_uuid,
            "label": tr.label,
            "speed": tr.speed,
            "path_history": json.loads(tr.path_history) if tr.path_history else []
        })

    analytics = compute_traffic_analytics(tracks_payload)
    return {"camera_id": camera_id, "traffic_analytics": analytics}


@router.get("/forensics/video-qa")
def natural_language_video_qa(question: str = Query(...), camera_id: str = Query(default=None), user=Depends(verify_viewer)):
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question parameter is required.")

    res = answer_video_question(question, camera_id=camera_id)
    return res
