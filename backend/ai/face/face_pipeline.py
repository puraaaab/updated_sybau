import os
import time
import urllib.request
import cv2
import uuid
import numpy as np
import threading
from ...config.service import get_models

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "models"))
YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

_detectors = {}  # (width, height) -> FaceDetectorYN
_recognizer = None
face_lock = threading.Lock()

def download_face_models():
    os.makedirs(MODELS_DIR, exist_ok=True)
    if not os.path.exists(YUNET_PATH):
        print("[FacePipeline] Downloading YuNet face detection ONNX model zoo weights...")
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        urllib.request.urlretrieve(url, YUNET_PATH)
    if not os.path.exists(SFACE_PATH):
        print("[FacePipeline] Downloading SFace face recognition ONNX model zoo weights...")
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
        urllib.request.urlretrieve(url, SFACE_PATH)

def _get_cv2_backend_target(device: str):
    has_cuda = (
        device == "cuda" and 
        hasattr(cv2, "cuda") and 
        cv2.cuda.getCudaEnabledDeviceCount() > 0 and 
        hasattr(cv2.dnn, "DNN_BACKEND_CUDA")
    )
    if has_cuda:
        return cv2.dnn.DNN_BACKEND_CUDA, cv2.dnn.DNN_TARGET_CUDA
    return cv2.dnn.DNN_BACKEND_DEFAULT, cv2.dnn.DNN_TARGET_CPU

def get_face_models(width=640, height=480):
    global _recognizer
    download_face_models()
    cfg = get_models()
    device = cfg.get("face", {}).get("device", "cuda")
    backend_id, target_id = _get_cv2_backend_target(device)

    with face_lock:
        key = (width, height)
        if key not in _detectors:
            try:
                det = cv2.FaceDetectorYN.create(
                    YUNET_PATH, "", (width, height), 0.6, 0.3, 100, backend_id, target_id
                )
            except Exception as e:
                print(f"[FacePipeline] OpenCV CUDA backend failed ({e}). Falling back to CPU.")
                det = cv2.FaceDetectorYN.create(
                    YUNET_PATH, "", (width, height), 0.6, 0.3, 100, cv2.dnn.DNN_BACKEND_DEFAULT, cv2.dnn.DNN_TARGET_CPU
                )
            _detectors[key] = det
        detector = _detectors[key]
            
        if _recognizer is None:
            try:
                rec = cv2.FaceRecognizerSF.create(
                    SFACE_PATH, "", backend_id, target_id
                )
            except Exception as e:
                print(f"[FacePipeline] OpenCV CUDA recognizer failed ({e}). Falling back to CPU.")
                rec = cv2.FaceRecognizerSF.create(
                    SFACE_PATH, "", cv2.dnn.DNN_BACKEND_DEFAULT, cv2.dnn.DNN_TARGET_CPU
                )
            _recognizer = rec
        return detector, _recognizer

_track_face_cache: dict = {}
_face_cache_lock = threading.Lock()
FACE_CACHE_TTL_SECONDS = 5.0

def process_faces(frame: np.ndarray, detections: list):
    """
    Detects faces for each tracked person in the frame with track-level caching.
    Uses YuNet for face detection and SFace for 128-dim face embeddings.
    """
    cfg = get_models()
    demo_mode = cfg.get("demo_mode", False)
    
    faces_detected = []
    people = [d for d in detections if d.get("class_name") == "person"]
    if not people:
        return faces_detected
    
    now_sec = time.time()

    # Check track-level face cache first (Option 1)
    uncached_people = []
    with _face_cache_lock:
        for p in people:
            t_uuid = p.get("track_uuid") or f"TRK_{p.get('camera_id', 'cam1')}_{p.get('track_id')}"
            cached = _track_face_cache.get(t_uuid)
            if cached and (now_sec - cached["cached_at"]) < FACE_CACHE_TTL_SECONDS:
                faces_detected.append(cached["data"])
            else:
                uncached_people.append(p)

    if not uncached_people:
        return faces_detected

    if demo_mode:
        for idx, person in enumerate(uncached_people):
            if (person["track_id"] + idx) % 3 == 0:
                face_id = str(uuid.uuid4())
                mock_embedding = np.random.normal(0, 1, 128).tolist()
                t_uuid = person.get("track_uuid") or f"TRK_{person.get('camera_id', 'cam1')}_{person['track_id']}"
                f_data = {
                    "track_uuid": t_uuid,
                    "face_bbox": [
                        person["bbox"][0] + 20, 
                        person["bbox"][1] + 10, 
                        person["bbox"][0] + 80, 
                        person["bbox"][1] + 70
                    ],
                    "confidence": 0.94,
                    "embedding": mock_embedding,
                    "embedding_id": face_id,
                    "label": "Person POI_09" if person["track_id"] % 2 == 0 else "Unknown"
                }
                faces_detected.append(f_data)
                with _face_cache_lock:
                    _track_face_cache[t_uuid] = {"data": f_data, "cached_at": now_sec}
        return faces_detected

    # Real Inference Mode using OpenCV FaceDetectorYN + FaceRecognizerSF
    try:
        h, w, _ = frame.shape
        # standardise YuNet detector input size to 640x480 to prevent ONNX assertion failures
        detector, recognizer = get_face_models(640, 480)
        
        # Resize original frame to 640x480 for detection
        det_frame = cv2.resize(frame, (640, 480))
        
        with face_lock:
            ret, faces = detector.detect(det_frame)
        if faces is not None:
            scale_x = w / 640.0
            scale_y = h / 480.0
            for face in faces:
                # Scale face coordinates (bbox and landmarks) back to original resolution space
                scaled_face = face.copy()
                scaled_face[0] *= scale_x  # x
                scaled_face[2] *= scale_x  # width
                for i in range(4, 14, 2):
                    scaled_face[i] *= scale_x
                
                scaled_face[1] *= scale_y  # y
                scaled_face[3] *= scale_y  # height
                for i in range(5, 14, 2):
                    scaled_face[i] *= scale_y

                bbox = scaled_face[0:4]
                xmin, ymin, width, height = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                confidence = float(scaled_face[14])
                
                # Align and crop face using scaled coordinates on original high-res frame
                with face_lock:
                    aligned_face = recognizer.alignCrop(frame, scaled_face)
                    embedding_feats = recognizer.feature(aligned_face) # shape: (1, 128)
                
                embedding_list = embedding_feats[0].tolist()
                
                # Geometric distance mapping to match face to closest person track
                best_track_uuid = None
                min_dist = float("inf")
                fx, fy = xmin + width / 2, ymin + height / 2
                
                for person in people:
                    pxmin, pymin, pxmax, pymax = person["bbox"]
                    if pxmin <= fx <= pxmax and pymin <= fy <= pymax:
                        px_center = (pxmin + pxmax) / 2
                        py_center = (pymin + pymax) / 2
                        dist = (fx - px_center)**2 + (fy - py_center)**2
                        if dist < min_dist:
                            min_dist = dist
                            best_track_uuid = person.get("track_uuid") or f"TRK_{person.get('camera_id', 'cam1')}_{person['track_id']}"
                            
                if best_track_uuid:
                    face_id = str(uuid.uuid4())
                    f_data = {
                        "track_uuid": best_track_uuid,
                        "face_bbox": [xmin, ymin, xmin + width, ymin + height],
                        "confidence": confidence,
                        "embedding": embedding_list,
                        "embedding_id": face_id,
                        "label": "Unknown",
                        "face_crop": aligned_face
                    }
                    faces_detected.append(f_data)
                    with _face_cache_lock:
                        if len(_track_face_cache) > 500:
                            _track_face_cache.clear()
                        _track_face_cache[best_track_uuid] = {"data": f_data, "cached_at": now_sec}
    except Exception as e:
        print(f"[FacePipeline] Error executing real face recognition: {e}")
        
    return faces_detected
