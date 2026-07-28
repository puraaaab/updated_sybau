import numpy as np
from ..detection.yolo import detect_and_track
from ..tracking.tracker import trajectory_tracker
from ..face.face_pipeline import process_faces
from ..vehicle.vehicle_reid import process_vehicles
from ..behavior.behavior_engine import behavior_engine
from ..captioning.captioner import generate_scene_caption
from ..embeddings.embedder import get_text_embedding
from ...config.service import get_models

def process_frame(frame: np.ndarray, camera_id: str, zones: list, alerts_cfg: dict, frame_idx: int) -> dict:
    """
    Coordinates frame analysis across all AI sub-modules by submitting tasks
    to the centralized Priority Queue Scheduler.

    GPU Scheduling Discipline (RTX 4060 8GB VRAM):
    ┌──────────────┬────────────────────────────────────┬──────────┐
    │ Model        │ Trigger Condition                  │ Device   │
    ├──────────────┼────────────────────────────────────┼──────────┤
    │ YOLO         │ Every sampled frame                │ CUDA     │
    │ Vehicle OCR  │ Only when vehicle class detected    │ CPU      │
    │ Vehicle ReID │ Only when vehicle class detected    │ CPU      │
    │ Face Det+Rec │ Only when person class detected     │ CPU      │
    │ Florence-2   │ Every N frames (configurable)       │ CUDA     │
    │ MiniLM Embed │ Only when caption is generated      │ CPU      │
    └──────────────┴────────────────────────────────────┴──────────┘

    This keeps YOLO and Florence-2 as the only GPU consumers, and they
    never run simultaneously (Florence runs on every Nth frame only).
    """
    from ..scheduler import inference_scheduler
    cfg = get_models()

    # 1. Object detection & tracking (YOLO + ByteTrack) — every frame, GPU
    def run_detection_and_tracking():
        raw_detections = detect_and_track(frame)
        return trajectory_tracker.update_tracks(raw_detections, camera_id)

    tracks = inference_scheduler.schedule_inference(
        inference_scheduler.PRIORITY_YOLO,
        run_detection_and_tracking
    )
    
    # 2. Process faces for tracked people — ONLY when person detected, CPU (Runs in parallel worker thread)
    faces = []
    people = [d for d in tracks if d.get("class_name") == "person"]
    if people and cfg.get("face", {}).get("enabled", True):
        faces = process_faces(frame, tracks)
    
    # 3. Process vehicle Re-ID & license plates — ONLY when vehicle detected, CPU (Runs in parallel worker thread)
    vehicles = []
    vehicle_classes = ["car", "truck", "motorcycle", "bus"]
    cars = [d for d in tracks if d.get("class_name") in vehicle_classes]
    if cars and cfg.get("vehicle", {}).get("enabled", True):
        vehicles = process_vehicles(frame, tracks)
    
    # 4. Evaluate behavior rules (CPU — lightweight, no model)
    #    Pass real frame dimensions so pixel bboxes normalize correctly against
    #    the 0–1 zone polygon coordinates stored in configs/zones.json.
    frame_height, frame_width = frame.shape[:2]
    alerts = behavior_engine.check_behaviors(tracks, zones, alerts_cfg, float(frame_width), float(frame_height))
    
    # 5. Scene captioning (Florence-2) — every N frames, GPU
    #    Configurable via models.json → florence.invoke_every_n_frames
    caption = None
    embedding = None
    try:
        florence_interval = max(1, int(cfg.get("florence", {}).get("invoke_every_n_frames", 30)))
    except (TypeError, ValueError):
        florence_interval = 30
    florence_enabled = cfg.get("florence", {}).get("enabled", True)
    
    if florence_enabled and frame_idx % florence_interval == 0:
        caption = inference_scheduler.schedule_inference(
            inference_scheduler.PRIORITY_FLORENCE,
            generate_scene_caption,
            frame
        )
        # 6. Text embedding — ONLY when caption is generated, CPU
        if caption:
            if vehicles:
                plates = [v["license_plate"] for v in vehicles if v.get("license_plate")]
                if plates:
                    caption += f" number plates detected: {', '.join(plates)}."
            embedding = get_text_embedding(caption)
            
    return {
        "tracks": tracks,
        "faces": faces,
        "vehicles": vehicles,
        "alerts": alerts,
        "caption": caption,
        "embedding": embedding
    }
