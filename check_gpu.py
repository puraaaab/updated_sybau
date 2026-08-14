import torch
import os, sys
sys.path.insert(0, r'c:\projects\sybau')
os.chdir(r'c:\projects\sybau')
from dotenv import load_dotenv
load_dotenv()

print("=== GPU Status ===")
cuda = torch.cuda.is_available()
print(f"CUDA available: {cuda}")
if cuda:
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
    props = torch.cuda.get_device_properties(0)
    print(f"GPU Memory: {props.total_memory // 1024**3} GB")
print()

from backend.config.service import get_models
cfg = get_models()
print("=== Config Devices ===")
print(f"YOLO device: {cfg.get('yolo', {}).get('device', 'NOT SET')}")
print(f"YOLO imgsz:  {cfg.get('yolo', {}).get('imgsz', 'NOT SET')}")
print(f"YOLO FPS:    {cfg.get('yolo', {}).get('sampling_rate_fps', 'NOT SET')}")
print(f"Face device: {cfg.get('face', {}).get('device', 'NOT SET')}")
print(f"Vehicle dev: {cfg.get('vehicle', {}).get('device', 'NOT SET')}")
print(f"Florence dev:{cfg.get('florence', {}).get('device', 'NOT SET')}")
print(f"Embedder dev:{cfg.get('embeddings', {}).get('device', 'NOT SET')}")
print()

# Check YOLO on GPU
print("=== YOLO GPU Check ===")
from ultralytics import YOLO
device = "cuda" if cuda else "cpu"
print(f"Loading YOLO on {device}...")
m = YOLO(r'c:\projects\sybau\yolo26l.pt')
m.to(device)
params = list(m.model.parameters())
print(f"YOLO param device: {params[0].device}")
print()

# YOLO predict test
import numpy as np
dummy = np.zeros((640, 640, 3), dtype=np.uint8)
res = m.predict(dummy, device=device, imgsz=640, verbose=False)
print(f"YOLO predict returned {len(res)} results on {device}")
print()

# Check SentenceTransformer on GPU
print("=== SentenceTransformer Embedder GPU Check ===")
from sentence_transformers import SentenceTransformer
emb_dev = cfg.get("embeddings", {}).get("device", "cpu")
print(f"Loading SentenceTransformer on {emb_dev}...")
st = SentenceTransformer("BAAI/bge-large-en-v1.5", device=emb_dev)
enc = st.encode("hello test", show_progress_bar=False)
print(f"Embedder device: {st.device}")
print(f"Embedding dim: {len(enc)}")
print()

print("=== ALL CHECKS PASSED ===")
