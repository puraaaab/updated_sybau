import logging

import numpy as np

from ..model_manager import model_manager

logger = logging.getLogger(__name__)

# COCO Class mapping for labels of interest (Tailored for Indian Street CCTV Surveillance)
COCO_CLASSES = {
    # People & Vehicles (0-8)
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    4: "airplane",
    5: "bus",
    6: "train",
    7: "truck",
    8: "boat",
    # Outdoor & Traffic (9-13)
    9: "traffic light",
    10: "fire hydrant",
    11: "stop sign",
    12: "parking meter",
    13: "bench",
    # Street Animals & Cattle (14-20)
    14: "bird",
    15: "cat",
    16: "dog",
    17: "horse",
    18: "sheep",
    19: "cow",
    20: "elephant",
    # Luggage, Carried Items & Sports/Weapons (24-38)
    24: "backpack",
    25: "umbrella",
    26: "handbag",
    28: "suitcase",
    34: "baseball bat",
    38: "tennis racket",
    # Food, Drinks & Tableware
    39: "bottle",
    43: "knife",
    46: "banana",
    47: "apple",
    48: "sandwich",
    49: "orange",
    51: "carrot",
    53: "pizza",
    55: "cake",
    # Furniture, Electronics & Personal Items
    56: "chair",
    59: "bed",
    61: "toilet",
    67: "cell phone",
    73: "book",
    77: "teddy bear"
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