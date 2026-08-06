import logging
import uuid
import threading
import torch
import numpy as np
import cv2
from PIL import Image
from ...config.service import get_models

logger = logging.getLogger(__name__)

_clip_model = None
_clip_lock = threading.Lock()
_person_cache = {}
_person_cache_lock = threading.Lock()

COLOR_MAP = {
    "red": ([0, 70, 50], [10, 255, 255]),
    "red2": ([156, 70, 50], [180, 255, 255]),
    "orange": ([11, 70, 50], [25, 255, 255]),
    "yellow": ([26, 70, 50], [35, 255, 255]),
    "green": ([36, 50, 50], [85, 255, 255]),
    "blue": ([86, 50, 50], [130, 255, 255]),
    "purple": ([131, 50, 50], [155, 255, 255]),
    "white": ([0, 0, 190], [180, 30, 255]),
    "black": ([0, 0, 0], [180, 255, 50]),
    "gray": ([0, 0, 51], [180, 45, 189])
}


def _get_clip_model():
    """Lazy loads SentenceTransformer with clip-ViT-B-32 vision-language model."""
    global _clip_model
    if _clip_model is not None:
        return _clip_model

    with _clip_lock:
        if _clip_model is None:
            cfg = get_models()
            if cfg.get("demo_mode", False):
                return None
            try:
                import torch
                from sentence_transformers import SentenceTransformer
                device = cfg.get("person", {}).get("device", "cuda" if torch.cuda.is_available() else "cpu")
                logger.info(f"Loading OpenCLIP vision model (clip-ViT-L-14) on {device}...")
                _clip_model = SentenceTransformer("clip-ViT-L-14", device=device)
                if device == "cuda" and hasattr(_clip_model, "half"):
                    try:
                        _clip_model.half()
                    except Exception:
                        pass
            except BaseException as e:
                logger.warning(f"Could not load SentenceTransformer clip-ViT-L-14: {e}")
                _clip_model = None

    return _clip_model


def get_clip_text_embedding(text_query: str) -> list:
    """Computes a 512-dimensional CLIP text embedding vector for natural language search."""
    model = _get_clip_model()
    if model is not None:
        try:
            return model.encode(text_query).tolist()
        except Exception as e:
            logger.warning(f"CLIP text encoding failed: {e}")

    # Fallback deterministic synthetic embedding (768d for clip-ViT-L-14)
    rng = np.random.default_rng(hash(text_query) % 4294967295)
    vec = rng.normal(0, 1, 768)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def extract_dominant_colors(crop_bgr: np.ndarray) -> dict:
    """Extracts dominant upper and lower body clothing colors from person crop."""
    try:
        h, w = crop_bgr.shape[:2]
        if h < 20 or w < 20:
            return {"upper_color": "unknown", "lower_color": "unknown"}

        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        upper_region = hsv[0:int(h * 0.5), :]
        lower_region = hsv[int(h * 0.5):h, :]

        def get_color(region):
            best_color = "unknown"
            max_pixels = 0
            total_pixels = region.shape[0] * region.shape[1]
            if total_pixels == 0:
                return "unknown"

            for color_name, (lower, upper) in COLOR_MAP.items():
                mask = cv2.inRange(region, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
                cnt = cv2.countNonZero(mask)
                if cnt > max_pixels:
                    max_pixels = cnt
                    best_color = "red" if color_name == "red2" else color_name

            return best_color if (max_pixels / float(total_pixels)) > 0.10 else "unknown"

        return {
            "upper_color": get_color(upper_region),
            "lower_color": get_color(lower_region)
        }
    except Exception:
        return {"upper_color": "unknown", "lower_color": "unknown"}



def process_person_crops(frame: np.ndarray, tracks: list, max_crop_embeddings: int = 25) -> list:
    """
    Extracts crops for tracked persons, computes 512-dimensional OpenCLIP vision-language
    embeddings, and determines visual attribute details.

    In dense crowd scenes, crops are ranked by resolution quality (area) to extract
    crisp OpenCLIP embeddings for top foreground/midground targets without VRAM overload.
    """
    person_tracks = [t for t in tracks if t.get("class_name") == "person"]
    if not person_tracks:
        return []

    # Sort person tracks by crop area (highest resolution first) for salience filtering in crowds
    def crop_area(t):
        b = t.get("bbox", [0, 0, 0, 0])
        return (b[2] - b[0]) * (b[3] - b[1])

    person_tracks_sorted = sorted(person_tracks, key=crop_area, reverse=True)

    model = _get_clip_model()
    results = []
    frame_h, frame_w = frame.shape[:2]

    # Process up to max_crop_embeddings top readable crops per frame pass
    for p in person_tracks_sorted[:max_crop_embeddings]:
        bbox = p.get("bbox", [])
        if len(bbox) < 4:
            continue

        if any(np.isnan(b) for b in bbox[:4]):
            continue

        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(frame_w, int(bbox[2]))
        y2 = min(frame_h, int(bbox[3]))

        crop_w = x2 - x1
        crop_h = y2 - y1

        if crop_w < 18 or crop_h < 35:
            continue  # Ignore tiny uninformative sub-pixel background specs

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        track_uuid = p.get("track_uuid")
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        
        # Motion-delta cache lookup: reuse OpenCLIP vector and attributes if displacement < 50px
        cached_entry = None
        if track_uuid:
            with _person_cache_lock:
                if track_uuid in _person_cache:
                    prev_cx, prev_cy = _person_cache[track_uuid]["centroid"]
                    dist = ((cx - prev_cx) ** 2 + (cy - prev_cy) ** 2) ** 0.5
                    if dist < 50.0:
                        cached_entry = _person_cache[track_uuid]

        if cached_entry is not None:
            vec = cached_entry["vec"]
            colors = cached_entry["colors"]
        else:
            colors = extract_dominant_colors(crop)
            vec = None
            if model is not None:
                try:
                    crop_rgb = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), (224, 224))
                    pil_img = Image.fromarray(crop_rgb)
                    with torch.inference_mode():
                        vec = model.encode(pil_img, show_progress_bar=False).tolist()
                except Exception as e:
                    logger.warning(f"CLIP encoding error for person crop: {e}")

            if vec is None:
                # Deterministic fallback synthetic vector (768d for clip-ViT-L-14)
                rng = np.random.default_rng(hash(track_uuid or "p") % 4294967295)
                vec = (rng.normal(0, 1, 768) / np.linalg.norm(rng.normal(0, 1, 768))).tolist()

            if track_uuid:
                with _person_cache_lock:
                    if len(_person_cache) > 1000:
                        _person_cache.clear()  # Clear cache if memory threshold reached
                    _person_cache[track_uuid] = {
                        "centroid": (cx, cy),
                        "vec": vec,
                        "colors": colors
                    }

        embedding_id = str(uuid.uuid4())

        results.append({
            "track_uuid": track_uuid,
            "bbox": [x1, y1, x2, y2],
            "embedding_id": embedding_id,
            "embedding": vec,
            "upper_color": colors["upper_color"],
            "lower_color": colors["lower_color"],
            "crowd_count": len(person_tracks),
            "crop": crop
        })

    return results
