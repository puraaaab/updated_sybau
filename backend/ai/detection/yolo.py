import logging
from typing import List, Dict, Any

import numpy as np

from ...config.service import get_models
from ..model_manager import model_manager

logger = logging.getLogger(__name__)

# COCO Class mapping for labels of interest (Tailored for Indian Street CCTV Surveillance)
COCO_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep",
    19: "cow", 20: "elephant", 24: "backpack", 25: "umbrella",
    26: "handbag", 28: "suitcase", 34: "baseball bat", 38: "tennis racket",
    39: "bottle", 43: "knife", 46: "banana", 47: "apple", 48: "sandwich",
    49: "orange", 51: "carrot", 53: "pizza", 55: "cake", 56: "chair",
    59: "bed", 61: "toilet", 67: "cell phone", 73: "book", 77: "teddy bear"
}

COCO_CLASS_IDS = list(COCO_CLASSES.keys())
DEFAULT_CONF_THRESHOLD = 0.4


def _confidence_threshold() -> float:
    try:
        return float(get_models().get("yolo", {}).get("confidence", DEFAULT_CONF_THRESHOLD))
    except (TypeError, ValueError):
        logger.warning("Invalid yolo.confidence configured; falling back to %.2f", DEFAULT_CONF_THRESHOLD)
        return DEFAULT_CONF_THRESHOLD


def _parse_result_boxes(result) -> List[Dict[str, Any]]:
    detections: List[Dict[str, Any]] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0 or not hasattr(boxes, "id") or boxes.id is None:
        return detections

    try:
        xyxy_list = boxes.xyxy.cpu().numpy()
        cls_list = boxes.cls.cpu().numpy()
        conf_list = boxes.conf.cpu().numpy()
        id_list = boxes.id.cpu().numpy()
    except Exception:
        logger.exception("Failed to convert YOLO boxes tensors to CPU numpy arrays.")
        return detections

    for i, track_id in enumerate(id_list):
        if np.isnan(track_id) or track_id < 0:
            continue
        if i >= len(cls_list) or i >= len(conf_list) or i >= len(xyxy_list):
            break
        cls_id = int(cls_list[i])
        class_name = COCO_CLASSES.get(cls_id)
        if class_name is None:
            continue
        detections.append({
            "track_id": int(round(track_id)),
            "class_name": class_name,
            "confidence": float(conf_list[i]),
            "bbox": [float(val) for val in xyxy_list[i]],
        })
    return detections


def detect_and_track(frame: np.ndarray):
    """Executes YOLO tracking on one camera frame."""
    try:
        yolo_model = model_manager.get_yolo()
        results = yolo_model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=COCO_CLASS_IDS,
            conf=_confidence_threshold(),
            verbose=False,
        )
    except Exception:
        logger.exception("YOLO track() failed for this frame; skipping.")
        return []

    if not results:
        return []
    return _parse_result_boxes(results[0])


def detect_and_track_batch(
    frames: List[np.ndarray],
    stream_ids: List[str],
    frame_counters: List[int],
    skip_interval: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """Executes batched YOLO tracking across multiple camera streams with selective frame skipping."""
    batch_detections = {stream_id: [] for stream_id in stream_ids}
    safe_skip_interval = max(1, int(skip_interval or 1))
    frames_to_process = []
    active_stream_indices = []

    for idx, (frame, _stream_id, count) in enumerate(zip(frames, stream_ids, frame_counters)):
        if count % safe_skip_interval == 0:
            frames_to_process.append(frame)
            active_stream_indices.append(idx)

    if not frames_to_process:
        return batch_detections

    try:
        yolo_model = model_manager.get_yolo()
        results = yolo_model.track(
            frames_to_process,
            persist=True,
            tracker="bytetrack.yaml",
            classes=COCO_CLASS_IDS,
            conf=_confidence_threshold(),
            verbose=False,
        )
    except Exception:
        logger.exception("Batched YOLO track() failed due to runtime/CUDA surge; skipping batch.")
        return batch_detections

    for batch_idx, result in enumerate(results or []):
        if batch_idx >= len(active_stream_indices):
            break
        orig_stream_idx = active_stream_indices[batch_idx]
        stream_id = stream_ids[orig_stream_idx]
        batch_detections[stream_id] = _parse_result_boxes(result)

    return batch_detections
