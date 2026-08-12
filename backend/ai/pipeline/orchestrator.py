import logging
import uuid
import datetime
import numpy as np
from ..detection.yolo import detect_and_track
from ..tracking.tracker import trajectory_tracker
from ..face.face_pipeline import process_faces
from ..vehicle.vehicle_reid import process_vehicles
from ..behavior.behavior_engine import behavior_engine
from ..captioning.captioner import generate_scene_caption, submit_async_scene_caption
from ..captioning.moondream_captioner import submit_moondream_caption
from ..embeddings.embedder import get_text_embedding
from ...config.service import get_models

logger = logging.getLogger(__name__)

# IST timezone constant (Indian Standard Time +05:30) used to stamp every frame at capture time
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def process_frame(frame: np.ndarray, camera_id: str, zones: list, alerts_cfg: dict, frame_idx: int) -> dict:
    from ..scheduler import inference_scheduler
    from ..captioning.captioner import record_yolo_frame_summary, submit_async_scene_caption
    cfg = get_models()

    florence_cfg = cfg.get("florence", {})
    florence_enabled = florence_cfg.get("enabled", True)
    n_frames = florence_cfg.get("invoke_every_n_frames", 1)

    # 0. PARALLEL DISPATCH: Send frame immediately to Florence in parallel with unique corr_id
    florence_queued = False
    corr_id = f"img_{uuid.uuid4().hex[:12]}"
    if florence_enabled and (n_frames <= 1 or frame_idx % n_frames == 0):
        try:
            # Stamp the exact IST wall-clock moment this frame was captured.
            # Embedded as ts= in the stored caption so the UI can show "captured X ago".
            # Fallback: empty string — caption stored without ts= rather than crashing.
            try:
                frame_ts = datetime.datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")
            except Exception:
                frame_ts = ""
            florence_queued = submit_async_scene_caption(
                frame,
                camera_id=camera_id,
                corr_id=corr_id,
                frame_ts=frame_ts,
            )
        except Exception as e:
            logger.warning(f"[{camera_id}] Parallel Florence dispatch error: {e}")

    # 1. Object detection & tracking (YOLO + ByteTrack) — batched GPU inference.
    #    Runs in parallel on the main thread for the same frame
    try:
        raw_detections = inference_scheduler.schedule_yolo_detection(camera_id, frame, frame_idx)
        tracks = trajectory_tracker.update_tracks(raw_detections, camera_id)
    except Exception as e:
        logger.warning(f"[{camera_id}] YOLO batched detection failed ({e}), falling back to direct inference.")
        try:
            raw_detections = detect_and_track(frame)
            tracks = trajectory_tracker.update_tracks(raw_detections, camera_id)
        except Exception as fallback_e:
            logger.warning(f"[{camera_id}] Fallback YOLO detection failed: {fallback_e}")
            tracks = []
    
    florence_cfg = cfg.get("florence", {})
    florence_enabled = florence_cfg.get("enabled", True)
    n_frames = florence_cfg.get("invoke_every_n_frames", 1)

    # 2. Process faces & person crops for tracked people — ONLY when person detected
    faces = []
    person_crops = []
    people = [d for d in tracks if d.get("class_name") == "person"]
    if people:
        if cfg.get("face", {}).get("enabled", True):
            faces = process_faces(frame, tracks)
        try:
            from ..person.person_attribute_engine import process_person_crops
            person_crops = process_person_crops(frame, tracks)
        except Exception as e:
            logger.warning(f"[{camera_id}] Person crop extraction failed: {e}")
    
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
    
    # 5. Build instant detailed frame scene caption with colors and attributes
    from ..vehicle.vehicle_reid import detect_crop_color
    description_parts = []
    
    # 5a. Vehicles with colors and license plates
    if vehicles:
        veh_counts: dict = {}
        for v in vehicles:
            v_color = v.get("vehicle_color", "")
            if isinstance(v_color, (tuple, list)):
                v_color = v_color[0]
            v_type = v.get("vehicle_type", "car")
            
            # Map Indian 3-wheeler geometry (COCO truck/car fallback to auto-rickshaw)
            if v_type in ("auto_rickshaw", "rickshaw", "tuktuk", "three_wheeler"):
                v_type = "auto-rickshaw"
            elif v_type in ("truck", "bus"):
                # Check bounding box aspect ratio: 3-wheelers are upright (w/h between 0.75 and 1.45)
                # YOLO frequently misclassifies Indian auto-rickshaws as 'truck' or 'bus'
                bbox = v.get("bbox") or [0, 0, 100, 100]
                bw, bh = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
                aspect = bw / float(bh)
                if 0.75 <= aspect <= 1.45 and bw < (frame_width * 0.4):
                    v_type = "auto-rickshaw"

            label = f"{v_color} {v_type}".strip() if v_color and v_color != "unknown" else v_type
            veh_counts[label] = veh_counts.get(label, 0) + 1
        for label, cnt in veh_counts.items():
            description_parts.append(f"{cnt} {label}")
        plates = [v["license_plate"] for v in vehicles if v.get("license_plate")]
        if plates:
            description_parts.append(f"license plates: {', '.join(plates)}")

    # 5b. People with upper & lower clothing colors
    if person_crops:
        p_counts: dict = {}
        for p in person_crops:
            u_col = p.get("upper_color", "unknown")
            if isinstance(u_col, (tuple, list)): u_col = u_col[0]
            l_col = p.get("lower_color", "unknown")
            if isinstance(l_col, (tuple, list)): l_col = l_col[0]
            if u_col != "unknown" and l_col != "unknown":
                p_label = f"person in {u_col} top and {l_col} bottom"
            elif u_col != "unknown":
                p_label = f"person in {u_col} top"
            elif l_col != "unknown":
                p_label = f"person in {l_col} bottom"
            else:
                p_label = "person"
            p_counts[p_label] = p_counts.get(p_label, 0) + 1
        for p_label, cnt in p_counts.items():
            description_parts.append(f"{cnt} {p_label}")
    else:
        person_count = sum(1 for t in tracks if t.get("class_name") == "person")
        if person_count > 0:
            description_parts.append(f"{person_count} person")

    # 5c. Non-vehicle/non-person objects (backpack, handbag, motorcycle, bicycle, etc.) with color detection
    non_person_non_vehicle = [
        t for t in tracks 
        if t.get("class_name") not in vehicle_classes and t.get("class_name") not in ("person", "license_plate")
    ]
    if non_person_non_vehicle:
        obj_counts: dict = {}
        for obj in non_person_non_vehicle:
            cls = obj.get("class_name", "object")
            bbox = obj.get("bbox", [])
            color = "unknown"
            if len(bbox) >= 4 and not any(np.isnan(b) for b in bbox[:4]):
                x1, y1, x2, y2 = max(0, int(bbox[0])), max(0, int(bbox[1])), min(frame_width, int(bbox[2])), min(frame_height, int(bbox[3]))
                if (x2 - x1) >= 15 and (y2 - y1) >= 15:
                    obj_crop = frame[y1:y2, x1:x2]
                    if obj_crop.size > 0:
                        color = detect_crop_color(obj_crop)
                        if isinstance(color, (tuple, list)): color = color[0]
            label = f"{color} {cls}".strip() if color and color != "unknown" else cls
            obj_counts[label] = obj_counts.get(label, 0) + 1
        for label, cnt in obj_counts.items():
            description_parts.append(f"{cnt} {label}")

    if not description_parts:
        description_parts = [f"{len(tracks)} objects"] if tracks else ["Active surveillance stream"]

    yolo_summary = ", ".join(description_parts)
    caption = f"[YOLO]: {yolo_summary} | camera {camera_id}"
    embedding = None

    # Record YOLO summary bound to this frame's correlation ID for parallel Florence
    record_yolo_frame_summary(corr_id, yolo_summary)

    # Dispatch Moondream captioner if enabled (interleaved on offset frames when both are active)
    moondream_cfg     = cfg.get("moondream", {})
    moondream_enabled = moondream_cfg.get("enabled", True)
    if moondream_enabled:
        md_n_frames      = moondream_cfg.get("invoke_every_n_frames", 4)
        # Interleave Moondream on frame offset (e.g. frame_idx % 4 == 2) when Florence is also active
        offset           = (md_n_frames // 2) if florence_enabled and md_n_frames > 1 else 0
        should_invoke_md = md_n_frames <= 1 or (frame_idx % md_n_frames == offset)
        if should_invoke_md:
            md_corr_id = uuid.uuid4().hex[:8]
            try:
                submit_moondream_caption(
                    frame, camera_id=camera_id, yolo_summary=yolo_summary, corr_id=md_corr_id
                )
            except Exception as e:
                logger.warning(f"[Moondream] Dispatch error on {camera_id}: {e}")


    # Instant text embedding for YOLO summary
    try:
        embedding = get_text_embedding(caption)
    except Exception as e:
        logger.warning(f"[{camera_id}] Text embedding failed: {e}")

    # Evaluate dynamic custom alert rules (license plates, natural language visual prompts, threats)
    custom_rules = alerts_cfg.get("custom_rules", []) if isinstance(alerts_cfg, dict) else []
    if custom_rules:
        try:
            from ..behavior.custom_rules import custom_rule_evaluator
            custom_alerts = custom_rule_evaluator.evaluate_custom_rules(
                {
                    "caption": caption,
                    "embedding": embedding,
                    "tracks": tracks,
                    "vehicles": vehicles
                },
                custom_rules,
                camera_id
            )
            alerts.extend(custom_alerts)
        except Exception as e:
            logger.warning(f"[{camera_id}] Custom rules evaluation note: {e}")
            
    return {
        "tracks": tracks,
        "faces": faces,
        "person_crops": person_crops,
        "vehicles": vehicles,
        "alerts": alerts,
        "caption": caption,
        "embedding": embedding,
        "florence_queued": florence_queued,
        # BUG-05 FIX: dominant YOLO class for this frame stored as structured
        # Qdrant payload field so semantic search can filter by class label.
        "dominant_class": _compute_dominant_class(tracks),
    }


def _compute_dominant_class(tracks: list) -> str | None:
    """Returns the most-detected object class in `tracks` by count.
    Used as the `yolo_class` payload field in the Qdrant scene vector so
    semantic search can apply a class-label filter to avoid cross-class
    mismatches (e.g. 'black car' matching a 'black motorcycle' caption).
    """
    if not tracks:
        return None
    counts: dict = {}
    for t in tracks:
        cls = t.get("class_name")
        if cls and cls != "license_plate":
            counts[cls] = counts.get(cls, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.__getitem__)

