import logging
import threading
import cv2
import numpy as np
import torch
import torchvision.models as models
import torchvision.transforms as transforms
import re
from PIL import Image
from ...config.service import get_models
from ..model_manager import model_manager
from .plate_parser import parse_plate

logger = logging.getLogger(__name__)

_reid_model = None
_preprocess = None
_reid_lock = threading.Lock()
_device = None
_track_plate_history = {}
_history_lock = threading.Lock()


def get_reid_model():
    """Thread-safe singleton getter for vehicle Re-ID model with CUDA acceleration."""
    global _reid_model, _preprocess, _device
    if _reid_model is None:
        with _reid_lock:
            if _reid_model is None:
                _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                logger.info(f"[VehicleReID] Initializing MobileNetV3-Small on {_device} for feature extraction...")
                weights = models.MobileNet_V3_Small_Weights.DEFAULT
                model = models.mobilenet_v3_small(weights=weights)
                model.classifier = torch.nn.Identity()
                model.eval()
                _reid_model = model.to(_device)

                _preprocess = transforms.Compose([
                    transforms.Resize((224, 224)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ])
    return _reid_model, _preprocess, _device


def find_plate_region(vehicle_crop: np.ndarray) -> np.ndarray:
    """Fallback HSV-based license plate localization when YOLO license_plate box is absent."""
    h, w = vehicle_crop.shape[:2]
    if h < 10 or w < 10:
        return vehicle_crop

    # Search full vehicle crop so plates on motorcycles, auto-rickshaws & tuktuks are detected
    hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, (15, 60, 60), (35, 255, 255))
    white_mask = cv2.inRange(hsv, (0, 0, 160), (180, 60, 255))
    mask = cv2.bitwise_or(yellow_mask, white_mask)

    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_box = None
    best_score = 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 12 or ch < 5:
            continue
        aspect = cw / float(ch)
        area = cw * ch
        if 1.5 <= aspect <= 8.0 and area > best_score:
            best_score = area
            best_box = (x, y, cw, ch)

    if best_box is None:
        # Fallback: lower 70% of crop
        return vehicle_crop[int(h * 0.3):, :]

    x, y, cw, ch = best_box
    pad_x, pad_y = int(cw * 0.08), int(ch * 0.15)
    x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
    x2, y2 = min(w, x + cw + pad_x), min(h, y + ch + pad_y)
    return vehicle_crop[y1:y2, x1:x2]


def enhance_for_ocr(plate_crop: np.ndarray):
    """Multi-stage image enhancement for Indian CCTV license plate crops."""
    if plate_crop is None or plate_crop.shape[0] < 5 or plate_crop.shape[1] < 5:
        return None, None, None

    # Scale to at least 60px tall — more pixels = better OCR accuracy
    scale = max(4.0, 60.0 / plate_crop.shape[0])
    resized = cv2.resize(plate_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    # Bilateral denoise — removes CCTV noise while preserving edges
    denoised = cv2.bilateralFilter(resized, d=9, sigmaColor=75, sigmaSpace=75)
    gray = cv2.cvtColor(denoised, cv2.COLOR_BGR2GRAY)

    # Unsharp masking for character edge crispening
    gaussian = cv2.GaussianBlur(gray, (0, 0), 2.0)
    sharpened = cv2.addWeighted(gray, 1.8, gaussian, -0.8, 0)

    # CLAHE — adaptive contrast for uneven lighting (night/sun glare)
    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(4, 4))
    contrast = clahe.apply(sharpened)

    # Standard binarization (light background, dark text — white plates)
    binarized = cv2.adaptiveThreshold(
        contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 4
    )
    # Inverted binarization for yellow / reflective plates (dark background, light text)
    binarized_inv = cv2.bitwise_not(binarized)

    return contrast, binarized, binarized_inv


def detect_vehicle_color(crop: np.ndarray) -> str:
    """
    Extracts dominant vehicle body color for search queries.
    Safely detects IR/monochrome night vision to avoid false 'white'/'silver' classifications.
    """
    try:
        h, w = crop.shape[:2]
        if h < 15 or w < 15:
            return "unknown"

        # Focus strictly on center vehicle hood/body (avoiding top windshield glass & bottom tires/asphalt)
        y1, y2 = int(h * 0.30), int(h * 0.75)
        x1, x2 = int(w * 0.20), int(w * 0.80)
        body_crop = crop[y1:y2, x1:x2]
        if body_crop.size == 0 or body_crop.shape[0] < 5 or body_crop.shape[1] < 5:
            body_crop = crop[:int(h * 0.7), int(w * 0.1):int(w * 0.9)]

        # Check for Nighttime IR (monochrome) camera feed: R, G, B channel means are virtually identical
        b_mean, g_mean, r_mean = cv2.mean(body_crop)[:3]
        channel_std = np.std([r_mean, g_mean, b_mean])
        if channel_std < 3.5:
            # Monochrome IR camera mode detected — color cannot be reliably determined
            return "unknown"

        hsv = cv2.cvtColor(body_crop, cv2.COLOR_BGR2HSV)
        
        # Use median color statistics to eliminate shadow/glare outliers
        h_val = float(np.median(hsv[:, :, 0]))
        s_val = float(np.median(hsv[:, :, 1]))
        v_val = float(np.median(hsv[:, :, 2]))

        if v_val < 50:
            return "black"
        elif v_val > 200 and s_val < 30:
            return "white"
        elif s_val < 40 and 50 <= v_val <= 200:
            return "silver"

        if h_val < 12 or h_val > 165:
            return "red"
        elif 12 <= h_val <= 30:
            return "yellow"
        elif 30 < h_val <= 85:
            return "green"
        elif 85 < h_val <= 130:
            return "blue"
        elif 130 < h_val <= 165:
            return "purple"

        return "black" if v_val < 100 else "silver"
    except Exception as e:
        logger.warning(f"[VehicleColor] Color extraction failed: {e}")
        return "unknown"


def process_vehicles(frame: np.ndarray, detections: list) -> list:
    """
    Identifies vehicles, extracts license plate crops (prioritizing YOLO license_plate boxes),
    runs multi-pass OCR, and generates GPU-accelerated Re-ID embeddings in single-pass batches.
    """
    cfg = get_models()
    demo_mode = cfg.get("demo_mode", False)

    vehicles_detected = []
    vehicle_classes = {
        "car", "truck", "motorcycle", "bus", "bicycle", "auto_rickshaw",
        "rickshaw", "tuktuk", "scooter", "moped", "van", "suv", "vehicle", "three_wheeler"
    }
    vehicles = [d for d in detections if d.get("class_name") in vehicle_classes]
    vehicles = [d for d in detections if d.get("class_name") in vehicle_classes]
    plate_detections = [d for d in detections if d.get("class_name") == "license_plate"]

    if demo_mode:
        for idx, veh in enumerate(vehicles):
            if (veh["track_id"] + idx) % 2 == 0:
                mock_plates = ["KA51MB8811", "DL3CQQ1234", "MH12DE5678", "TX99VMS"]
                plate_text = mock_plates[veh["track_id"] % len(mock_plates)]
                vehicles_detected.append({
                    "track_uuid": f"track_{veh['track_id']}",
                    "license_plate": plate_text,
                    "ocr_confidence": 0.96,
                    "vehicle_type": veh["class_name"],
                    "vehicle_color": "black" if idx % 2 == 0 else "white",
                    "reid_vector": None,
                    "reid_valid": False
                })
        return vehicles_detected

    if not vehicles:
        return []

    reid_model, preprocess, device = get_reid_model()

    ocr_obj = model_manager.get_ocr()
    if isinstance(ocr_obj, tuple):
        ocr_type, reader = ocr_obj
    else:
        ocr_type, reader = "mock", ocr_obj

    # Stage 1: Crop vehicles & build batch tensor for GPU Re-ID
    valid_vehicle_items = []
    tensors_list = []

    h, w, _ = frame.shape

    for veh in vehicles:
        bbox = veh["bbox"]
        ymin, ymax = int(max(0, bbox[1])), int(min(h, bbox[3]))
        xmin, xmax = int(max(0, bbox[0])), int(min(w, bbox[2]))

        if ymax - ymin < 25 or xmax - xmin < 25:
            continue

        crop = frame[ymin:ymax, xmin:xmax]
        vehicle_color = detect_vehicle_color(crop)

        # Build tensor input for batched GPU inference
        try:
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            crop_pil = Image.fromarray(crop_rgb)
            tensor_input = preprocess(crop_pil)
            tensors_list.append(tensor_input)
        except Exception as e:
            logger.error(f"[VehicleReID] Image preprocessing failed for track {veh.get('track_id')}: {e}")
            tensors_list.append(None)

        # Check for explicit YOLO license_plate box inside this vehicle box
        matched_plate_crop = None
        for p_det in plate_detections:
            px1, py1, px2, py2 = map(int, p_det["bbox"])
            if px1 >= xmin and py1 >= ymin and px2 <= xmax and py2 <= ymax:
                p_ymin, p_ymax = max(0, py1), min(h, py2)
                p_xmin, p_xmax = max(0, px1), min(w, px2)
                if p_ymax - p_ymin > 5 and p_xmax - p_xmin > 5:
                    matched_plate_crop = frame[p_ymin:p_ymax, p_xmin:p_xmax]
                    break

        if matched_plate_crop is None:
            matched_plate_crop = find_plate_region(crop)

        valid_vehicle_items.append({
            "veh": veh,
            "crop": crop,
            "plate_crop": matched_plate_crop,
            "vehicle_color": vehicle_color,
        })

    # Stage 2: Batched GPU Re-ID forward pass
    reid_vectors = [None] * len(valid_vehicle_items)
    reid_valid_flags = [False] * len(valid_vehicle_items)

    valid_indices = [i for i, t in enumerate(tensors_list) if t is not None]
    if valid_indices and reid_model is not None:
        try:
            batch_tensor = torch.stack([tensors_list[i] for i in valid_indices]).to(device)
            with torch.no_grad():
                features = reid_model(batch_tensor)  # shape: (B, 576)
                features_np = features.cpu().numpy()

                for idx, orig_idx in enumerate(valid_indices):
                    feat_vec = features_np[idx]
                    norm = np.linalg.norm(feat_vec)
                    if norm > 1e-6:
                        feat_vec = feat_vec / norm
                        reid_vectors[orig_idx] = feat_vec.tolist()
                        reid_valid_flags[orig_idx] = True
        except Exception as e:
            logger.exception(f"[VehicleReID] Batched Re-ID inference failed on {device}: {e}")

    # Stage 3: Multi-pass OCR on extracted license plate crops
    for i, item in enumerate(valid_vehicle_items):
        veh = item["veh"]
        plate_crop = item["plate_crop"]
        vehicle_color = item["vehicle_color"]

        plate_text = None
        ocr_conf = 0.0

        if plate_crop is not None and plate_crop.size > 0 and plate_crop.shape[0] >= 10 and plate_crop.shape[1] >= 10:
            try:
                gray_enhanced, binarized, binarized_inv = enhance_for_ocr(plate_crop)
                if gray_enhanced is not None:
                    ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                    MIN_CHAR_CONF = 0.45

                    best_text = None
                    best_conf = 0.0

                    for img_variant in [binarized, binarized_inv, gray_enhanced]:
                        try:
                            if ocr_type == "paddleocr":
                                pd_res = reader.ocr(img_variant, cls=False)
                                res = []
                                if pd_res and pd_res[0]:
                                    for sub in pd_res[0]:
                                        bbox_coords, (txt, conf) = sub
                                        res.append((bbox_coords, txt, float(conf)))
                            else:
                                res = reader.readtext(
                                    img_variant,
                                    allowlist=ALLOWLIST,
                                    min_size=10,
                                    text_threshold=0.5,
                                    link_threshold=0.4,
                                    low_text=0.3,
                                )
                        except Exception as ocr_err:
                            logger.warning(f"[OCR] Sub-pass extraction failed: {ocr_err}")
                            res = []

                        if not res:
                            continue

                        # Filter out low-confidence single-char garbage reads
                        res = [r for r in res if r[2] >= MIN_CHAR_CONF and len(r[1]) >= 3]
                        if not res:
                            continue

                        res.sort(key=lambda r: (r[0][0][1] // 10, r[0][0][0]))
                        combined_raw = "".join([r[1].upper() for r in res])
                        avg_conf = sum(r[2] for r in res) / len(res)

                        parsed_res = parse_plate(combined_raw)
                        target_text = parsed_res["parsed"] if parsed_res.get("parsed") else (combined_raw if len(combined_raw) >= 4 else None)
                        if target_text and avg_conf > best_conf:
                            best_text = target_text
                            best_conf = avg_conf

                    if best_text:
                        plate_text = best_text
                        ocr_conf = float(best_conf)
            except Exception as e:
                logger.error(f"[OCR] Plate OCR failed for track {veh.get('track_id')}: {e}")

        # Multi-frame Tracklet License Plate Consensus Voting
        track_key = veh.get('track_id')
        if track_key is not None:
            with _history_lock:
                if track_key not in _track_plate_history:
                    _track_plate_history[track_key] = []
                if plate_text:
                    _track_plate_history[track_key].append((plate_text, ocr_conf))
                    if len(_track_plate_history[track_key]) > 10:
                        _track_plate_history[track_key].pop(0)

                # Compute consensus plate string via weighted frequency voting
                history = _track_plate_history[track_key]
                if history:
                    votes = {}
                    for p_str, p_conf in history:
                        votes[p_str] = votes.get(p_str, 0.0) + p_conf
                    consensus_plate = max(votes.items(), key=lambda x: x[1])[0]
                    plate_text = consensus_plate
                    ocr_conf = max(p_conf for p_str, p_conf in history if p_str == consensus_plate)

        # Explicit audited failure fields (no random vector pollution)
        vehicles_detected.append({
            "track_uuid": f"track_{veh['track_id']}",
            "license_plate": plate_text,
            "ocr_confidence": ocr_conf,
            "vehicle_type": veh["class_name"],
            "vehicle_color": vehicle_color,
            "reid_vector": reid_vectors[i],
            "reid_valid": reid_valid_flags[i]
        })

    return vehicles_detected
