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

_reid_model = None

def find_plate_region(vehicle_crop):
    h, w = vehicle_crop.shape[:2]
    lower_half = vehicle_crop[int(h * 0.4):, :]
    
    hsv = cv2.cvtColor(lower_half, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, (15, 80, 80), (35, 255, 255))
    white_mask = cv2.inRange(hsv, (0, 0, 170), (180, 60, 255))
    mask = cv2.bitwise_or(yellow_mask, white_mask)
    
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_box = None
    best_score = 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 15 or ch < 6: continue
        aspect = cw / float(ch)
        area = cw * ch
        if 1.8 <= aspect <= 7.0 and area > best_score:
            best_score = area
            best_box = (x, y, cw, ch)
            
    if best_box is None:
        fx1, fy1 = int(w * 0.25), int(lower_half.shape[0] * 0.4)
        fx2, fy2 = int(w * 0.75), lower_half.shape[0]
        return lower_half[fy1:fy2, fx1:fx2]
        
    x, y, cw, ch = best_box
    pad_x, pad_y = int(cw * 0.08), int(ch * 0.15)
    x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
    x2, y2 = min(lower_half.shape[1], x + cw + pad_x), min(lower_half.shape[0], y + ch + pad_y)
    return lower_half[y1:y2, x1:x2]

def enhance_for_ocr(plate_crop):
    """Multi-stage image enhancement for Indian CCTV license plate crops."""
    if plate_crop.shape[0] < 5 or plate_crop.shape[1] < 5:
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

_preprocess = None

def get_reid_model():
    global _reid_model, _preprocess
    if _reid_model is None:
        print("[VehicleReID] Initializing torchvision MobileNetV3-Small for feature extraction...")
        # Load pre-trained weights
        weights = models.MobileNet_V3_Small_Weights.DEFAULT
        _reid_model = models.mobilenet_v3_small(weights=weights)
        # Remove classifier block to return global pooled features (576 dims)
        _reid_model.classifier = torch.nn.Identity()
        _reid_model.eval()
        
        _preprocess = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    return _reid_model, _preprocess


def detect_vehicle_color(crop: np.ndarray) -> str:
    """Extracts dominant vehicle body color for natural language search queries (e.g. 'black TATA car')."""
    try:
        h, w = crop.shape[:2]
        if h < 15 or w < 15:
            return "unknown"
        body_crop = crop[:int(h * 0.7), int(w * 0.1):int(w * 0.9)]
        if body_crop.size == 0:
            return "unknown"

        hsv = cv2.cvtColor(body_crop, cv2.COLOR_BGR2HSV)
        v_val = float(np.mean(hsv[:, :, 2]))
        s_val = float(np.mean(hsv[:, :, 1]))
        h_val = float(np.mean(hsv[:, :, 0]))

        if v_val < 55:
            return "black"
        elif v_val > 195 and s_val < 35:
            return "white"
        elif s_val < 45 and 55 <= v_val <= 195:
            return "silver"

        if h_val < 10 or h_val > 170:
            return "red"
        elif 15 <= h_val <= 35:
            return "yellow"
        elif 35 < h_val <= 85:
            return "green"
        elif 85 < h_val <= 130:
            return "blue"
        elif 130 < h_val <= 170:
            return "purple"

        return "dark" if v_val < 125 else "light"
    except Exception:
        return "unknown"


def process_vehicles(frame: np.ndarray, detections: list):
    """
    Identifies vehicles, extracts license plate crops, runs OCR, 
    and generates visual Re-ID feature embeddings.
    """
    cfg = get_models()
    demo_mode = cfg.get("demo_mode", False)
    
    vehicles_detected = []
    vehicle_classes = ["car", "truck", "motorcycle", "bus"]
    vehicles = [d for d in detections if d.get("class_name") in vehicle_classes]
    
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
                    "reid_vector": np.random.normal(0, 1, 576).tolist()
                })
        return vehicles_detected

    # Real Inference Mode using PaddleOCR/EasyOCR and torchvision MobileNetV3 Re-ID
    ocr_obj = model_manager.get_ocr()
    if isinstance(ocr_obj, tuple):
        ocr_type, reader = ocr_obj
    else:
        ocr_type, reader = "mock", ocr_obj

    reid_model, preprocess = get_reid_model()
    
    for veh in vehicles:
        bbox = veh["bbox"]
        h, w, _ = frame.shape
        
        # Crop full vehicle image for Re-ID
        ymin, ymax = int(max(0, bbox[1])), int(min(h, bbox[3]))
        xmin, xmax = int(max(0, bbox[0])), int(min(w, bbox[2]))
        
        if ymax - ymin < 25 or xmax - xmin < 25:
            continue
            
        crop = frame[ymin:ymax, xmin:xmax]
        vehicle_color = detect_vehicle_color(crop)
        
        # Compute visual Re-ID vector embedding
        try:
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            crop_pil = Image.fromarray(crop_rgb)
            input_tensor = preprocess(crop_pil).unsqueeze(0)
            
            with torch.no_grad():
                features = reid_model(input_tensor) # shape: (1, 576)
                feat_vec = features[0].numpy()
                feat_vec = feat_vec / (np.linalg.norm(feat_vec) + 1e-6)
                # Use full 576‑dim vector (no truncation)
                reid_vector = feat_vec.tolist()
        except Exception as e:
            print(f"[VehicleReID] Feature extraction error: {e}")
            reid_vector = np.random.normal(0, 1, 576).tolist()

        plate_text = None
        ocr_conf = 0.0
        
        if crop.shape[0] >= 40 and crop.shape[1] >= 40:
            try:
                plate_crop = find_plate_region(crop)
                if plate_crop is not None and plate_crop.size > 0:
                    gray_enhanced, binarized, binarized_inv = enhance_for_ocr(plate_crop)
                    if gray_enhanced is not None:
                        ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                        MIN_CHAR_CONF = 0.35  # discard any single read below this

                        best_text = None
                        best_conf = 0.0
                        best_parsed = None

                        # Multi-pass OCR: try binarized, inverted, and grayscale
                        for img_variant in [binarized, binarized_inv, gray_enhanced]:
                            try:
                                if ocr_type == "paddleocr":
                                    pd_res = reader.ocr(img_variant, cls=False)
                                    res = []
                                    if pd_res and pd_res[0]:
                                        for item in pd_res[0]:
                                            bbox_coords, (txt, conf) = item
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
                            except Exception:
                                if hasattr(reader, 'readtext'):
                                    res = reader.readtext(img_variant, allowlist=ALLOWLIST)
                                else:
                                    res = []

                            if not res:
                                continue

                            # Filter out low-confidence single-char garbage reads
                            res = [r for r in res if r[2] >= MIN_CHAR_CONF or len(r[1]) > 2]
                            if not res:
                                continue

                            # Sort geometrically: top-to-bottom, left-to-right
                            res.sort(key=lambda r: (r[0][0][1] // 10, r[0][0][0]))
                            combined_raw = "".join([r[1].upper() for r in res])
                            avg_conf = sum(r[2] for r in res) / len(res)

                            parsed_res = parse_plate(combined_raw)
                            if parsed_res["parsed"] is not None and avg_conf > best_conf:
                                best_text = parsed_res["parsed"]
                                best_conf = avg_conf
                                best_parsed = parsed_res

                        if best_text:
                            plate_text = best_text
                            ocr_conf = float(best_conf)
            except Exception as e:
                print(f"[VehicleReID] Plate OCR error: {e}")

        # Always return the track Re-ID vector, attaching license plate text if detected
        vehicles_detected.append({
            "track_uuid": f"track_{veh['track_id']}",
            "license_plate": plate_text,
            "ocr_confidence": ocr_conf,
            "vehicle_type": veh["class_name"],
            "vehicle_color": vehicle_color,
            "reid_vector": reid_vector
        })
            
    return vehicles_detected
