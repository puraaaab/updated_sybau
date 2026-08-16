import json
from typing import Optional, List, Dict, Any
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Track
from ..auth.helpers import verify_viewer, verify_operator
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

    florence_cfg = get_models().get("florence", {})
    florence_enabled = florence_cfg.get("enabled", False)
    moondream_cfg = get_models().get("moondream", {})
    moondream_enabled = moondream_cfg.get("enabled", True)

    yolo_name = getattr(model_manager, "_yolo_model_name", "YOLO")
    
    # All active enabled models must be loaded for overall READY status
    all_ready = (
        yolo_loaded 
        and ocr_loaded 
        and embedder_loaded 
        and (not florence_enabled or florence_loaded)
    )

    models_dict = {
        yolo_name: "LOADED" if yolo_loaded else "LOADING",
        "OCR": "LOADED" if ocr_loaded else "LOADING",
        "Embedder": "LOADED" if embedder_loaded else "LOADING",
    }
    if florence_enabled:
        models_dict["Florence"] = "LOADED" if florence_loaded else "LOADING"
    if moondream_enabled:
        models_dict["Moondream"] = "CLOUD_READY"

    return {
        "status": "READY" if all_ready else "PREWARMING",
        "all_ready": all_ready,
        "models": models_dict
    }


@router.get("/camera-telemetry")
def get_cameras_telemetry(user=Depends(verify_viewer)):
    return get_latest_telemetry()


@router.get("/analytics/heatmap")
def get_spatial_heatmap_data(camera_id: str = Query(default="cam_1"), user=Depends(verify_viewer), db: Session = Depends(get_db)):
    recent_tracks = db.query(Track).filter(Track.camera_id == camera_id).order_by(Track.last_seen.desc()).limit(40).all()
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
    recent_tracks = db.query(Track).filter(Track.camera_id == camera_id).order_by(Track.last_seen.desc()).limit(50).all()
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


# ─────────────────────────────────────────────────────────────────────────────
# Audio Intelligence & Acoustic Anomaly Endpoints (FEAT-01)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analytics/audio-events")
def list_audio_events(
    camera_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    is_anomaly: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Retrieves paginated audio intelligence events and acoustic anomaly telemetry (RBAC: Viewer+)."""
    from ..database.models import AudioEvent
    q = db.query(AudioEvent)
    if camera_id:
        q = q.filter(AudioEvent.camera_id == camera_id)
    if event_type:
        q = q.filter(AudioEvent.event_type == event_type.lower())
    if is_anomaly is not None:
        q = q.filter(AudioEvent.is_anomaly == is_anomaly)

    total = q.count()
    records = q.order_by(AudioEvent.timestamp.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "event_uuid": r.event_uuid,
                "camera_id": r.camera_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "duration_seconds": r.duration_seconds,
                "event_type": r.event_type,
                "is_anomaly": r.is_anomaly,
                "classifier_name": r.classifier_name,
                "confidence": r.confidence,
                "anomaly_score": r.anomaly_score,
                "decibels": r.decibels,
                "peak_frequency_hz": r.peak_frequency_hz,
            }
            for r in records
        ]
    }


@router.post("/cameras/{camera_id}/audio-chunk")
def ingest_camera_audio_chunk(
    camera_id: str,
    payload: dict,
    user=Depends(verify_operator),
):
    """
    Ingests a raw 16kHz mono 16-bit PCM audio chunk for real-time acoustic AI processing (RBAC: Operator+).
    Payload can contain base64_pcm (string) or simulated decibels/frequency params.
    """
    import base64
    from ..ai.audio.acoustic_engine import production_audio_engine

    base64_data = payload.get("base64_pcm")
    if base64_data:
        try:
            pcm_bytes = base64.b64decode(base64_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64_pcm payload.")
    else:
        # Generate synthetic 16kHz sine wave PCM chunk from provided frequency and decibel level
        freq = float(payload.get("frequency_hz", 1000.0))
        db = float(payload.get("decibels", 70.0))
        duration_sec = float(payload.get("duration_sec", 1.0))
        sample_rate = 16000
        t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
        # Amplitude derived from dB RMS: 0 dB = 1.0, 90 dB = 10^(90/20) scaled to int16 range
        rms_target = 10.0 ** (db / 20.0)
        amplitude = min(32767.0, rms_target * np.sqrt(2))
        waveform = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16)
        pcm_bytes = waveform.tobytes()

    events = production_audio_engine.process_pcm_chunk(camera_id, pcm_bytes)
    return {
        "status": "success",
        "camera_id": camera_id,
        "bytes_processed": len(pcm_bytes),
        "events_detected": len(events),
        "events": events
    }
