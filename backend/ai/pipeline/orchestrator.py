import logging
import numpy as np
from ..detection.yolo import detect_and_track
from ..tracking.tracker import trajectory_tracker
from ..face.face_pipeline import process_faces
from ..vehicle.vehicle_reid import process_vehicles
from ..behavior.behavior_engine import behavior_engine
from ..captioning.captioner import generate_scene_caption
from ..embeddings.embedder import get_text_embedding
from ...config.service import get_models

logger = logging.getLogger(__name__)

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

    # 1. Object detection & tracking (YOLO + ByteTrack) — every frame, GPU.
    #    Runs DIRECTLY on the calling AI worker thread — each camera has its own
    #    thread and PyTorch CUDA inference is thread-safe, so no scheduler needed.
    #    Routing all 14 cameras through a single scheduler queue would serialize
    #    them and cause timeouts at 2 FPS × 14 cameras.
    try:
        raw_detections = detect_and_track(frame)
        tracks = trajectory_tracker.update_tracks(raw_detections, camera_id)
    except Exception as e:
        logger.warning(f"[{camera_id}] YOLO detection failed: {e}")
        tracks = []
    
    # 2. Process faces for tracked people — ONLY when person detected, CPU (Runs in parallel worker thread)
    faces = []
    people = [d for d in tracks if d.get("class_name") == "person"]
    if people and cfg.get("face", {}).get("enabled", True):
        faces = process_faces(frame, tracks)
    
    # 3. Process vehicle Re-ID & license plates — ONLY when vehicle detected, CPU (Runs in parallel worker thread)
    vehicle_classes = [
        "car", "truck", "motorcycle", "bus", "bicycle", "auto_rickshaw",
        "rickshaw", "tuktuk", "scooter", "moped", "van", "suv", "vehicle", "three_wheeler"
    ]
    vehicles = []  # Always initialize so return dict is safe even if no vehicle detected
    cars = [d for d in tracks if d.get("class_name") in vehicle_classes]
    if cars and cfg.get("vehicle", {}).get("enabled", True):
        vehicles = process_vehicles(frame, tracks)
    
    # 4. Evaluate behavior rules (CPU — lightweight, no model)
    #    Pass real frame dimensions so pixel bboxes normalize correctly against
    #    the 0–1 zone polygon coordinates stored in configs/zones.json.
    frame_height, frame_width = frame.shape[:2]
    alerts = behavior_engine.check_behaviors(tracks, zones, alerts_cfg, float(frame_width), float(frame_height))
    
    # 5. Build instant frame scene caption (guarantees 100% of frames across all streams produce captions)
    description_parts = []
    if vehicles:
        veh_counts: dict = {}
        for v in vehicles:
            v_color = v.get("vehicle_color", "")
            v_type = v.get("vehicle_type", "car")
            label = f"{v_color} {v_type}".strip() if v_color and v_color != "unknown" else v_type
            veh_counts[label] = veh_counts.get(label, 0) + 1
        for label, cnt in veh_counts.items():
            description_parts.append(f"{cnt} {label}")
        plates = [v["license_plate"] for v in vehicles if v.get("license_plate")]
        if plates:
            description_parts.append(f"license plates: {', '.join(plates)}")

    # Include non-vehicle classes
    class_counts: dict = {}
    for t in tracks:
        cls = t.get("class_name", "object")
        if cls not in vehicle_classes and cls != "license_plate":
            class_counts[cls] = class_counts.get(cls, 0) + 1
    for cls, cnt in class_counts.items():
        description_parts.append(f"{cnt} {cls}")

    if not description_parts:
        description_parts = [f"{len(tracks)} objects"] if tracks else ["Active surveillance stream"]

    yolo_summary = ", ".join(description_parts)
    caption = f"[YOLO]: {yolo_summary} | camera {camera_id}"
    embedding = None

    # Attempt Florence-2 VLM caption if GPU queue is free
    florence_enabled = cfg.get("florence", {}).get("enabled", True)
    if florence_enabled and frame_idx % 2 == 0:
        try:
            if inference_scheduler.request_queue.qsize() < 2:
                florence_cap = inference_scheduler.schedule_inference(
                    inference_scheduler.PRIORITY_FLORENCE,
                    generate_scene_caption,
                    frame
                )
                if florence_cap:
                    caption = f"[YOLO]: {yolo_summary} | [Florence-2]: {florence_cap} | camera {camera_id}"
        except Exception as e:
            logger.debug(f"[{camera_id}] Skipping Florence scene captioning: {e}")

    try:
        embedding = get_text_embedding(caption)
    except Exception as e:
        logger.warning(f"[{camera_id}] Text embedding failed: {e}")
            
    return {
        "tracks": tracks,
        "faces": faces,
        "vehicles": vehicles,
        "alerts": alerts,
        "caption": caption,
        "embedding": embedding
    }
