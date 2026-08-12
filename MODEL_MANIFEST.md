# SYBAU AI Model Manifest & License Compliance

This manifest documents every machine learning model used within the SYBAU AI Surveillance & Video Management System, including exact checkpoint provenance, embedding dimensions, licenses, and execution backends.

| Model Identifier | Core Model Name | Exact Checkpoint / Weight Tag | Source / Repository | License | Input Type / Size | Output Vector / Schema | Runtime Backend | Hardware Requirement |
|------------------|-----------------|-------------------------------|---------------------|---------|-------------------|------------------------|-----------------|----------------------|
| `yolov8n` | YOLOv8 Nano | `yolov8n.pt` / `v8.0` | Ultralytics (`ultralytics/yolov8`) | AGPL-3.0 / Enterprise | Image BGR / 640x640 | Bounding Boxes, Classes, Confidence | PyTorch / TensorRT / ONNX | CPU / CUDA (1GB VRAM) |
| `easyocr` | EasyOCR Engine | `craft_mlt_25k` + `latin_g2` | JaidedAI (`jaidedai/easyocr`) | Apache-2.0 | Image Crop / Dynamic | License Plate Text, OCR Confidence | PyTorch / CUDA | CPU / CUDA (1GB VRAM) |
| `sface` | OpenCV SFace | `face_recognition_sface_2021dec.onnx` | OpenCV Model Zoo (`opencv/opencv_zoo`) | Apache-2.0 | Face Crop 112x112 | 128D Float Embedding Vector | OpenCV DNN / ONNX | CPU / CUDA (<500MB VRAM) |
| `osnet` | Omni-Scale Re-ID (OSNet) | `osnet_x1_0_imagenet.pth` / `osnet_x1_0` | Torchreid (`KaiyangZhou/deep-person-reid`) | MIT | Person Crop 256x128 | 512D Float Appearance Vector | PyTorch / ONNX | CPU / CUDA (1GB VRAM) |
| `fastreid` | FastReID Vehicle | `res50_ibn_a_veri776.pth` | FastReID (`DenseCL/fast-reid` on VeRi-776) | Apache-2.0 | Vehicle Crop 224x224 | 2048D Float Vehicle Vector | PyTorch / ONNX | CPU / CUDA (1GB VRAM) |
| `florence2` | Florence-2 Large | `microsoft/Florence-2-large` | HuggingFace Hub | MIT | Image RGB / Dynamic | Detailed Scene Description Text | Transformers / PyTorch | CUDA (4GB VRAM required) |
| `yamnet` | YAMNet Audio Classifier | `yamnet_onnx_v1.onnx` | TensorFlow Hub / ONNX Model Zoo | Apache-2.0 | 16kHz PCM Audio Buffer | 521 Audio Event Class Probabilities | ONNX Runtime / PyTorch | CPU / CUDA (<500MB VRAM) |
| `all-minilm-l6-v2` | SentenceTransformer Embedder | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace (`sentence-transformers`) | Apache-2.0 | Natural Language Text | 384D Dense Vector Embedding | PyTorch / ONNX Runtime | CPU / CUDA (<500MB VRAM) |

---

### Model License & Data Provenance Verification
1. **OSNet Person Re-ID**: Licensed under **MIT License**. Checkpoint `osnet_x1_0` trained on Market-1501 / MSMT17 / DukeMTMC. Output is a 512D L2-normalized float feature vector.
2. **FastReID Vehicle**: Licensed under **Apache-2.0**. Checkpoint `res50_ibn_a` trained on VeRi-776 dataset. Output is a 2048D L2-normalized float feature vector.
3. **YAMNet ONNX**: Licensed under **Apache-2.0**. Checkpoint `yamnet_onnx_v1` trained on AudioSet dataset. Output is a 521-element probability vector over standard audio event classes (e.g. scream, gunshot, explosion, glass break).
