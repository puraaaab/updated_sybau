import logging

import numpy as np

from ..model_manager import model_manager

logger = logging.getLogger(__name__)

# COCO Class mapping for labels of interest
COCO_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    32: "umbrella"
}

COCO_CLASS_IDS = list(COCO_CLASSES.keys())
CONF_THRESHOLD = 0.4


def detect_and_track(frame: np.ndarray):
    """
    Executes YOLO model tracking on the given frame.
    Returns:
        List of dicts containing:
        - track_id (int) — stable ByteTrack ID. Detections without a
          confirmed track ID yet are dropped, not given a fake ID.
        - class_name (str)
        - confidence (float)
        - bbox (list: [x1, y1, x2, y2])
    """
    detections = []

    try:
        yolo_model = model_manager.get_yolo()
        results = yolo_model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=COCO_CLASS_IDS,
            conf=CONF_THRESHOLD,
            verbose=False,
        )
    except Exception:
        logger.exception("YOLO track() failed for this frame; skipping.")
        return detections

    if not results:
        return detections

    result = results[0]
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return detections

    # If the tracker hasn't confirmed IDs yet (e.g. very first frames),
    # id_list will be None. We deliberately do NOT fabricate track IDs —
    # a made-up ID is worse than no detection, since downstream dedup /
    # evidence logic treats track_id as a stable identity.
    if not hasattr(boxes, "id") or boxes.id is None:
        return detections

    xyxy_list = boxes.xyxy.cpu().numpy()
    cls_list = boxes.cls.cpu().numpy()
    conf_list = boxes.conf.cpu().numpy()
    id_list = boxes.id.cpu().numpy()

    for i in range(len(boxes)):
        cls_id = int(cls_list[i])
        class_name = COCO_CLASSES.get(cls_id)
        if class_name is None:
            # Shouldn't happen since classes=COCO_CLASS_IDS was passed to
            # track(), but keep as a defensive guard.
            continue

        detections.append({
            "track_id": int(id_list[i]),
            "class_name": class_name,
            "confidence": float(conf_list[i]),
            "bbox": [float(val) for val in xyxy_list[i]]
        })

    return detections