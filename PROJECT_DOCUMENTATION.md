# PROJECT_DOCUMENTATION.md
> **Ground-truth, line-by-line audit of the entire Sybau VMS repository.**
> Every claim is traceable to a specific file and line number. No placeholders, no guesses.

---

## TABLE OF CONTENTS
1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Technology Stack](#3-technology-stack)
4. [Architecture Overview](#4-architecture-overview)
5. [Data Flow / Pipeline](#5-data-flow--pipeline)
6. [AI / ML Models](#6-ai--ml-models)
7. [API Reference](#7-api-reference)
8. [Database Schema](#8-database-schema)
9. [Configuration Files](#9-configuration-files)
10. [Environment Variables](#10-environment-variables)
11. [Key Features](#11-key-features)
12. [Infrastructure / Docker](#12-infrastructure--docker)
13. [Setup & Running Locally](#13-setup--running-locally)
14. [Security Model](#14-security-model)
15. [Known Issues / Limitations](#15-known-issues--limitations)
16. [Dependency Index](#16-dependency-index)

---

## 1. Project Overview

**Sybau VMS** (Video Management System) is a real-time AI-powered surveillance platform built for Indian smart-city deployments -- specifically Surat, Gujarat.

Key capabilities:
- Multi-camera live grid monitoring (RTSP/HLS/WebRTC/YouTube)
- GPU-accelerated object detection and multi-object tracking (YOLO + ByteTrack)
- Behavior analysis: loitering, running, crowd density, restricted areas, wrong direction, abandoned objects
- Face recognition and Person-of-Interest (POI) watchlisting
- Vehicle Re-ID and license plate OCR (PaddleOCR / EasyOCR)
- Scene captioning via Florence-2 (local) or Moondream 3.1 (cloud API)
- Natural language semantic video search (vector embeddings + Qdrant)
- Forensic evidence export (SHA-256 signed ZIP packages)
- FIR evidence report generation (HTML, SHA-256 case hash)
- E-Challan traffic citation generation with QR code
- Real-time WebSocket alert push
- Role-based access control: admin / operator / viewer
- DPDP-compliant watchlist retention tracking (90-day purge)

---

## 2. Repository Structure

```
sybau_granth/
├── backend/
│   ├── main.py                          # App entry, lifespan, router mounting, WebSocket
│   ├── ai/
│   │   ├── model_manager.py             # Singleton loader: YOLO, OCR, Florence-2
│   │   ├── scheduler.py                 # Priority-queue GPU micro-batch scheduler
│   │   ├── behavior/
│   │   │   ├── behavior_engine.py       # BehaviorEngine — all alert checks
│   │   │   ├── restricted.py            # Restricted area detector
│   │   │   ├── loitering.py             # Loitering time-threshold detector
│   │   │   ├── running.py               # Speed-based running detector
│   │   │   ├── crowd.py                 # Crowd density checker
│   │   │   ├── wrong_direction.py       # Wrong-direction line-crossing
│   │   │   ├── abandoned_object.py      # Abandoned-object detector
│   │   │   └── custom_rules.py          # NLP-based user-defined alert rules
│   │   ├── captioning/
│   │   │   ├── captioner.py             # Florence-2 round-robin scheduler
│   │   │   ├── moondream_captioner.py   # Moondream cloud API captioner
│   │   │   └── caption_integrity.py     # SHA-256 image-to-caption binding
│   │   ├── detection/
│   │   │   ├── yolo.py                  # YOLO detect_and_track wrapper (COCO filter)
│   │   │   └── batch_collector.py       # DeadlinedBatchCollector (GPU throttle)
│   │   ├── embeddings/
│   │   │   └── embedder.py              # SentenceTransformer BAAI/bge-large-en-v1.5
│   │   ├── face/
│   │   │   └── face_pipeline.py         # YuNet + SFace face detection & embedding
│   │   ├── person/
│   │   │   ├── person_attribute_engine.py # Clothing color, gender, posture & bag detection
│   │   │   └── person_reid.py           # MobileNetV3 Person Re-ID embedding generator
│   │   ├── routing/
│   │   │   └── downstream_router.py     # Task router between YOLO, Florence, Moondream & Person models
│   │   ├── tracking/
│   │   │   └── tracker.py               # TrajectoryTracker (speed + path history)
│   │   ├── vehicle/
│   │   │   └── vehicle_reid.py          # MobileNetV3 Re-ID + HSV plate localization
│   │   ├── pipeline/
│   │   │   └── orchestrator.py          # Per-frame AI pipeline orchestration
│   │   ├── privacy/
│   │   │   └── redactor.py              # Gaussian blur for face/plate redaction
│   │   ├── audio/
│   │   │   └── acoustic_engine.py       # FFT-based acoustic anomaly detector
│   │   └── workers/
│   │       └── secondary_consumers.py   # Async background vector indexing & heavy tasks worker
│   ├── admin/
│   │   └── router.py                    # Admin: user management + audit log routes
│   ├── auth/
│   │   ├── router.py                    # Login, register, change-password routes
│   │   └── helpers.py                   # JWT creation, role guards, password hash
│   ├── config/
│   │   └── service.py                   # Config loader for JSON config files
│   ├── database/
│   │   ├── connection.py                # SQLAlchemy engine + SessionLocal
│   │   └── models.py                    # All ORM table models (14 tables)
│   ├── messaging/
│   │   └── kafka_client.py              # KafkaProducer + MemoryEventBus fallback
│   ├── monitoring/
│   │   ├── health.py                    # System vitals (CPU, RAM, GPU, DB, Qdrant)
│   │   ├── camera_state.py              # CameraStateMachine states
│   │   └── metrics.py                   # Prometheus metrics text generator
│   ├── recording/
│   │   ├── recorder.py                  # CameraRecorder (30s MP4 segments)
│   │   └── retention.py                 # RetentionManager (30 days / 85% disk cap)
│   ├── routers/
│   │   ├── analytics.py                 # Heatmap, traffic speed, AI status, telemetry
│   │   ├── cameras.py                   # Camera CRUD, ONVIF scan, MJPEG stream
│   │   ├── playback.py                  # Alerts history, alert ACK, snapshot serve
│   │   ├── proxy.py                     # SSRF-protected HLS/M3U8 proxy
│   │   ├── ptz.py                       # PTZ control stub
│   │   ├── records.py                   # Face/vehicle/plate/caption/OCR ledger
│   │   ├── rules.py                     # Custom alert rule CRUD
│   │   ├── search.py                    # Semantic + license plate + face search
│   │   └── settings.py                  # System settings endpoint
│   ├── scripts/
│   │   ├── seed_rtsp_cams.py            # Seeds cameras.json into DB on startup
│   │   └── nvr_emulator.py              # Loops local MP4 into RTSP via FFmpeg
│   ├── search/
│   │   ├── vector_search.py             # Qdrant + in-memory cosine semantic search
│   │   └── qdrant_utils.py              # Qdrant client factory + timeout helpers
│   ├── services/
│   │   ├── bwc_ingest.py                # Offline/batch Body-Worn Camera media ingestion
│   │   ├── bwc_live_ingest.py           # Body-Worn Camera live stream ingestion
│   │   ├── challan.py                   # E-Challan HTML citation + QR code
│   │   ├── co_occurrence.py             # Spatial-temporal co-occurrence graph
│   │   ├── event_export.py              # Alert evidence ZIP builder (SHA-256)
│   │   ├── fir_report.py                # FIR evidence report (HTML, SHA-256)
│   │   ├── forensics.py                 # Custom forensic clip export (FFmpeg)
│   │   ├── identity.py                  # GlobalIdentityManager (cross-cam face merge)
│   │   ├── nvr_adapter.py               # Third-party NVR integration adapter
│   │   ├── onvif_discovery.py           # ONVIF WS-Discovery UDP scanner service
│   │   ├── onvif_ptz.py                 # ONVIF PTZ SOAP control service
│   │   ├── ptz_tracker.py               # Automated target PTZ tracking service
│   │   ├── stream_manager.py            # CameraStream + StreamManager (frame bus)
│   │   ├── stream_resolver.py           # RTSP/YouTube URL resolution + cache
│   │   ├── traffic_analytics.py         # Speed/flow traffic analytics
│   │   ├── trajectory.py                # Subject trajectory map route
│   │   ├── video_qa.py                  # NL video question answering
│   │   └── watchlist.py                 # Watchlist (POI) CRUD + DPDP purge
│   ├── storage/
│   │   └── minio_client.py              # boto3 MinIO S3 client (local FS fallback)
│   ├── tests/                           # Backend component tests (11 test files)
│   │   ├── test_bwc_ingest.py
│   │   ├── test_caption_integrity.py
│   │   ├── test_onvif_discovery.py
│   │   ├── test_ssrf_proxy.py
│   │   └── ...
│   ├── utils/
│   │   ├── audit.py                     # log_audit_event() helper
│   │   ├── security.py                  # safe_join_path() path traversal guard
│   │   ├── ssrf.py                      # SSRF validator (IP range / DNS rebinding)
│   │   └── timezone.py                  # IST timezone utilities
│   └── workers/
│       └── ai_worker.py                 # CameraAIWorker + index_vector + telemetry
├── frontend/
│   ├── index.html                       # HTML entrypoint
│   ├── package.json                     # Frontend dependencies (React 19, MUI, HLS.js, Recharts)
│   ├── vite.config.js                   # Vite config & dev proxies
│   └── src/
│       ├── main.jsx                     # Application root render entry point
│       ├── index.css                    # Design system tokens & global glassmorphism CSS
│       ├── App.jsx                      # Root component, auth, nav, IST clock
│       └── components/
│           ├── LiveGrid.jsx
│           ├── AlertsPanel.jsx
│           ├── InvestigationSearch.jsx
│           ├── AdminConsole.jsx
│           ├── WatchlistManager.jsx
│           ├── ArchivePlayback.jsx
│           ├── DiscoveryScanner.jsx
│           ├── ForensicsManager.jsx
│           ├── SettingsConsole.jsx
│           ├── TrajectoryMap.jsx
│           ├── RecordsConsole.jsx
│           ├── CameraManagement.jsx
│           └── LoginModal.jsx
├── tests/                               # Root automated test suite (19 test files)
│   ├── test_vms.py
│   ├── test_concurrency.py
│   ├── test_batch_collector_stress.py
│   ├── test_kafka_and_n1_performance.py
│   └── ...
├── docs/                                # Project technical reports
│   ├── KNOWN_LIMITATIONS_AND_ROADMAP.md
│   ├── LOAD_TEST_RESULTS.md
│   ├── bug_feature_report.md
│   └── repo_gap_report.md
├── configs/
│   ├── alerts.json                      # Per-camera alert thresholds
│   ├── cameras.json                     # Static camera definitions (seeded to DB)
│   ├── models.json                      # AI model paths, demo_mode flag
│   ├── privacy.json                     # Global privacy redaction settings
│   └── zones.json                       # Zone polygon definitions
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py       # Adds status, must_change_password, deleted_at
├── models/
│   ├── face_detection_yunet_2023mar.onnx
│   └── face_recognition_sface_2021dec.onnx
├── storage/
│   ├── recordings/                      # 30-second MP4 segments per camera
│   ├── snapshots/                       # JPEG snapshots per alert/track
│   ├── exports/                         # Forensic evidence ZIP packages
│   └── h264_cache/                      # H.264-converted clips for web playback
├── logs/
│   ├── backend.log
│   ├── frontend.log
│   └── nvr.log
├── Dockerfile.backend                   # Multi-stage Python 3.10 OpenCV/FFmpeg backend Docker image
├── Dockerfile.frontend                  # Multi-stage Node 20 / Nginx reverse proxy frontend Docker image
├── docker-compose.yml
├── .env / .env.example
├── requirements.txt
├── reset_vms_data.py                    # Database, storage & vector collection wipe utility
├── write_docs.py                        # Documentation generation script
├── manage.ps1                           # Windows PowerShell start/stop/restart
├── AUDIT_REMEDIATION_REPORT.md          # Security & compliance fix report
├── setup_guide.md                       # Environment setup guide
├── usecase.md                           # Enterprise deployment use-cases
└── PROJECT_DOCUMENTATION.md
```

---

## 3. Technology Stack

### Backend
| Layer | Technology | Source |
|---|---|---|
| Web Framework | FastAPI (async ASGI) | `backend/main.py:167` |
| ASGI Server | Uvicorn | `manage.ps1:111` |
| ORM | SQLAlchemy | `backend/database/connection.py` |
| Migrations | Alembic | `alembic/versions/0001_initial_schema.py` |
| Auth | JWT (python-jose, HS256) + bcrypt | `backend/auth/helpers.py` |
| Object Detection | Ultralytics YOLO | `backend/ai/model_manager.py:111` |
| Tracking | ByteTrack (via `tracker="bytetrack.yaml"`) | `backend/ai/model_manager.py:21` |
| Scene Captioning (local) | Florence-2 `microsoft/Florence-2-base` | `backend/ai/model_manager.py:234` |
| Scene Captioning (cloud) | Moondream 3.1 REST API | `backend/ai/captioning/moondream_captioner.py:43` |
| Text Embeddings | SentenceTransformer `BAAI/bge-large-en-v1.5` (1024d) | `backend/ai/embeddings/embedder.py:12` |
| Vector DB | Qdrant (4 vector spaces: face, scene, vehicle, person_crop) | `backend/search/qdrant_utils.py` |
| Face Detection | YuNet ONNX (`cv2.FaceDetectorYN`) | `backend/ai/face/face_pipeline.py:51` |
| Face Recognition | SFace ONNX (`cv2.FaceRecognizerSF`) | `backend/ai/face/face_pipeline.py:64` |
| Person Re-ID | MobileNetV3 (768d feature vector) | `backend/ai/person/person_reid.py:22` |
| Vehicle Re-ID | MobileNetV3-Small (torchvision, 576d Identity head) | `backend/ai/vehicle/vehicle_reid.py:36` |
| License Plate OCR | PaddleOCR (primary) / EasyOCR (fallback) | `backend/ai/model_manager.py:144-183` |
| Stream Ingest | OpenCV (GStreamer NVDEC -> FFmpeg CUDA -> fallback) | `backend/services/stream_manager.py:91-116` |
| YouTube Resolution | yt-dlp | `backend/services/stream_resolver.py:15` |
| Rate Limiting | SlowAPI | `backend/auth/router.py:23` |
| Testing Framework | Pytest | `tests/`, `backend/tests/` |
| Event Bus | Apache Kafka + MemoryEventBus fallback | `backend/messaging/kafka_client.py:26-52` |
| Object Storage | MinIO S3 (boto3) + local FS fallback | `backend/storage/minio_client.py:24-55` |
| Video Processing | FFmpeg (subprocess) | `backend/services/forensics.py:146-165` |
| Metrics | Prometheus text format | `backend/main.py:227-230` |
| WebSocket | FastAPI native WebSocket | `backend/main.py:252-263` |

### Frontend
| Layer | Technology | Source |
|---|---|---|
| Build Tool | Vite + `@vitejs/plugin-react` | `frontend/vite.config.js:1-5` |
| UI Framework | React 19 (`react^19.2.7`) | `frontend/package.json` |
| Component Library | Material UI (MUI) v5 + Lucide React | `frontend/package.json` |
| Video Streaming | HLS.js (`hls.js^1.6.16`) | `frontend/package.json` |
| Analytics Charts | Recharts (`recharts^3.9.2`) | `frontend/package.json` |
| Routing | React Router v7 (`react-router-dom^7.18.1`) | `frontend/package.json` |
| Dev Proxy (REST) | `/api -> http://127.0.0.1:8000` | `frontend/vite.config.js:10-26` |
| Dev Proxy (WS) | `/ws -> ws://127.0.0.1:8000` | `frontend/vite.config.js:28-39` |
| Dev Proxy (HLS) | `/hls -> http://127.0.0.1:8888` | `frontend/vite.config.js:41-51` |
| Dev Proxy (WebRTC) | `/webrtc -> http://127.0.0.1:8889` | `frontend/vite.config.js:53-63` |

### Infrastructure (Docker & Containers)
| Service | Image / File | Ports | Purpose |
|---|---|---|---|
| Backend API | `Dockerfile.backend` (Python 3.10 slim + OpenCV + FFmpeg) | 8000 | FastAPI ASGI backend |
| Frontend UI | `Dockerfile.frontend` (Node 20 build stage -> Nginx alpine) | 80 | Static assets + reverse proxy |
| PostgreSQL | `postgres:15` | 5432 | Primary relational database |
| Qdrant | `qdrant/qdrant:latest` | 6333, 6334 | Multi-space vector similarity search |
| MediaMTX | `bluenviron/mediamtx` | 8554, 8888, 8889 | RTSP -> HLS/WebRTC relay |
| MinIO | `minio/minio:latest` | 9000, 9001 | S3-compatible object storage |
| Kafka | `confluentinc/cp-kafka:7.6.0` | 9092 | Event streaming |
| ZooKeeper | `confluentinc/cp-zookeeper:7.6.0` | 2181 | Kafka coordination |

---

## 4. Architecture Overview

```
RTSP Cameras / YouTube / Body-Worn Cameras
        |
        v
StreamManager / CameraStream (stream_manager.py)
  Priority: GStreamer NVDEC -> FFmpeg CUDA -> OpenCV -> sub-stream failover
  Reconnect backoff: 2s -> doubles -> 60s cap (MAX_RECONNECT_WAIT=60, line 17)
  Reference counting: ref_count per stream (line 31)
        |
   +---------+------------------+
   |                            |
CameraAIWorker             CameraRecorder
(ai_worker.py)             (recorder.py)
Every N frames             30s MP4 segments (mp4v)
                           -> FFmpeg H.264 transcode (h264_cache/)
        |
        v
InferenceScheduler (scheduler.py)
  Priority queue (PriorityQueue, line 29)
  15ms GPU micro-batch window (MAX_BATCH_ACCUMULATION_WAIT_SECONDS=0.015, line 26)
  Max YOLO batch: 8 (MAX_YOLO_BATCH_SIZE=8, line 25)
        |
        v
AI Pipeline Orchestrator (orchestrator.py)
  1. YOLO detect+track (yolo.py)
     COCO filter: person(0), bicycle(1), car(2), motorbike(3), bus(5), truck(7)
  2. TrajectoryTracker (tracker.py)
     - Path history: last 30 centroids per (camera_id, track_id)
     - Speed: EMA (0.7 * prev + 0.3 * instant, line 65)
  3. BehaviorEngine (behavior_engine.py)
     - Restricted / Loitering / Running / Crowd / WrongDirection / Abandoned
     - Cooldown dedup per (track_id, alert_type, sub_key), default 30s
  4. Face Pipeline (face_pipeline.py)
     - YuNet detect (conf 0.6, NMS IOU 0.3)
     - SFace 128-dim embed
     - GlobalIdentityManager cosine match (>=0.40)
  5. Vehicle Re-ID (vehicle_reid.py)
     - MobileNetV3-Small feature extraction
     - HSV plate localization (yellow/white mask, aspect 1.5-8.0)
     - PaddleOCR / EasyOCR plate read
  6. Florence / Moondream captioning
     - Round-robin scheduler across cameras
     - SHA-256 image-to-caption integrity binding
  7. Custom Rule Evaluator (custom_rules.py)
     - Plate wildcard / class keyword / semantic NLP matching
        |
   +----+----------+-------------+
   |               |             |
PostgreSQL       Qdrant       Kafka / MemoryEventBus
(Alerts,Tracks,  vms_embed-   -> WebSocket broadcast
 Faces,Vehicles) dings coll.  -> /api/v1/ws/alerts
                               -> React frontend
```

### Concurrency Model
- **AI_Startup thread** (`main.py:152`): Single daemon thread loads all models and launches workers.
- **Per-camera threads**: Each `CameraAIWorker` and `CameraRecorder` has its own daemon thread.
- **GPU serialization**: `model_manager.gpu_lock` (`threading.Lock()`, `model_manager.py:89`) serializes CUDA inference.
- **Batch aggregation**: `InferenceScheduler` collects frames into PriorityQueue, flushes within 15ms window.
- **Florence round-robin**: `FlorenceRoundRobinScheduler` dispatches across cameras fairly (`captioner.py:93`).
- **Async persistence**: `ThreadPoolExecutor(max_workers=4)` for non-blocking JPEG snapshot writes (`captioner.py:18`).

---

## 5. Data Flow / Pipeline

### Frame Ingestion
1. `CameraStream._capture_loop()` (`stream_manager.py:163`) runs per camera in a dedicated thread.
2. Stream open priority:
   a. GStreamer NVDEC: `rtspsrc ... nvh264dec ... appsink` (`stream_manager.py:93-103`)
   b. FFmpeg CUDA: `cv2.VideoCapture(url, cv2.CAP_FFMPEG)` (`stream_manager.py:106-112`)
   c. Native OpenCV: `cv2.VideoCapture(url)` (`stream_manager.py:115-116`)
   d. Sub-stream failover: 101->102, main->sub, subtype=0->subtype=1 (`stream_manager.py:138-158`)
3. Each frame stored in `CameraStream.latest_frame` under `_lock`.
4. On 50 consecutive failures -> reconnect with exponential backoff (`stream_manager.py:180, 174`).
5. Local file sources (MP4): loops back to frame 0 on EOF (`stream_manager.py:199-204`).

### AI Worker Loop
1. `CameraAIWorker._worker_loop()` calls `stream.get_latest_frame()` periodically.
2. Submits frame to `InferenceScheduler.schedule_yolo_detection()` (blocking until GPU batch returns).
3. Orchestrator pipelines: YOLO -> Trajectory -> Behavior -> Face -> Vehicle -> Captioning -> Custom Rules.
4. Alert dicts written as `Alert` rows to PostgreSQL.
5. `event_client.publish_event()` -> Kafka (or MemoryEventBus) -> `broadcast_event_to_websockets()`.
6. Active WebSocket clients on `/api/v1/ws/alerts` receive JSON push.

### Snapshot & Vector Storage
1. JPEG snapshots -> `storage/snapshots/{track_uuid}.jpg` via `ThreadPoolExecutor`.
2. Track, Face, Vehicle, SceneCaption rows committed to PostgreSQL.
3. `index_vector()` -> Qdrant `vms_embeddings` collection + `model_manager.vector_db` list fallback.

### Recording & Retention
1. `CameraRecorder._recording_loop()` writes `storage/recordings/{cam_id}/YYYYMMDD_HHMMSS.mp4` (30s, mp4v).
2. Background FFmpeg thread converts each segment to H.264 into `storage/h264_cache/`.
3. `RetentionManager` (`retention.py`): runs hourly, deletes >30-day files, enforces 85% disk cap.
4. Alert-linked recordings are protected from deletion (checked via `alert.video_url` filename match).

---

## 6. AI / ML Models

### 6.1 YOLO + ByteTrack
- **File**: `backend/ai/model_manager.py:96-126`, `backend/ai/detection/yolo.py`
- **Default model**: `yolo26l.pt` (`model_manager.py:114`)
- **Config key**: `configs/models.json -> yolo.model_path`
- **Device**: cuda if available, else cpu (`model_manager.py:121`)
- **Tracker**: `bytetrack.yaml` (`model_manager.py:21`)
- **COCO filter**: person(0), bicycle(1), car(2), motorbike(3), bus(5), truck(7)
- **Confidence**: `configs/models.json -> yolo.conf`
- **Demo**: `MockYOLO` returns 2 synthetic boxes (`model_manager.py:60-63`)

### 6.2 YuNet (Face Detection)
- **Model**: `models/face_detection_yunet_2023mar.onnx` (`face_pipeline.py:9`)
- **Source**: OpenCV Zoo (auto-downloaded on first run)
- **Confidence**: 0.6 score, 0.3 NMS IOU, max 100 faces (`face_pipeline.py:52`)
- **Backend**: DNN_BACKEND_CUDA if available, else DNN_BACKEND_DEFAULT (`face_pipeline.py:30-38`)

### 6.3 SFace (Face Recognition)
- **Model**: `models/face_recognition_sface_2021dec.onnx` (`face_pipeline.py:10`)
- **Embedding**: 128-dimensional
- **Identity match threshold**: cosine similarity >= 0.40 (`identity.py:43`)

### 6.4 MobileNetV3-Small (Vehicle Re-ID)
- **File**: `backend/ai/vehicle/vehicle_reid.py:24-46`
- **Weights**: `MobileNet_V3_Small_Weights.DEFAULT` (torchvision)
- **Head**: `model.classifier = torch.nn.Identity()` (feature extraction only)
- **Input**: 224x224, ImageNet normalization
- **Plate localization**: HSV yellow/white mask, aspect ratio 1.5-8.0 (`vehicle_reid.py:57-74`)

### 6.5 PaddleOCR / EasyOCR
- **File**: `backend/ai/model_manager.py:128-183`
- **Priority**: PaddleOCR -> EasyOCR -> MockOCR
- **PaddleOCR v3.x API**: `use_textline_orientation=False` (`model_manager.py:156`)
- **PaddleOCR v2.x API**: `use_angle_cls=False` (`model_manager.py:160`)
- **GPU**: auto-detected via `torch.cuda.is_available()`
- **Startup probe**: 32x128 gray image fed at init to verify engine health (`model_manager.py:157-162`)

### 6.6 Florence-2 (Local Scene Captioning)
- **File**: `backend/ai/model_manager.py:185-267`, `backend/ai/captioning/captioner.py`
- **Model**: `microsoft/Florence-2-base` (configurable via `florence.model_id`)
- **Prompt**: `<MORE_DETAILED_CAPTION>` (`captioner.py:31`)
- **Dispatch interval**: 0.5s min between batches (`captioner.py:34-43`)
- **Batch size**: 2 cameras/dispatch (`captioner.py:61-67`)
- **Max new tokens**: 1024 (`captioner.py:49-55`)
- **dtype**: float16 on CUDA, float32 on CPU (`model_manager.py:236`)
- **flash_attn**: patched via MagicMock stub to suppress ImportError (`model_manager.py:208-231`)
- **Integrity binding**: SHA-256 per frame, single-use token (`caption_integrity.py:37-100`)
- **Demo**: MockFlorence returns fixed string (`model_manager.py:79-81`)

### 6.7 Moondream 3.1 (Cloud Scene Captioning)
- **File**: `backend/ai/captioning/moondream_captioner.py`
- **API**: `https://api.moondream.ai/v1/query` (`moondream_captioner.py:43`)
- **Model**: `moondream3.1-9B-A2B` (env: `MOONDREAM_MODEL`)
- **Auth**: round-robin over `MOONDREAM_API_KEYS` (comma-separated) (`moondream_captioner.py:50-77`)
- **Timeout**: 30s/request (`moondream_captioner.py:44`)

### 6.8 SentenceTransformer (Text Embeddings)
- **File**: `backend/ai/embeddings/embedder.py`
- **Model**: `BAAI/bge-large-en-v1.5` (1024-dim, `embedder.py:12`)
- **Cache**: in-process `_embedding_cache` dict
- **Demo**: deterministic MD5-seeded NumPy mock (`embedder.py:18-30`)

### 6.9 Acoustic Anomaly Detector
- **File**: `backend/ai/audio/acoustic_engine.py`
- **Method**: RMS dBFS + FFT peak frequency analysis on 16-bit mono 16kHz PCM
- **Classes**:
  - gunshot: >=95 dB, rise_time 15ms, freq <3000 Hz
  - scream: >=85 dB, freq 2000-5000 Hz
  - glass_break: >=80 dB, freq 4000-8000 Hz
  - explosion: >=105 dB, rise_time 30ms
- **Status**: logic implemented; audio capture loop from RTSP not yet integrated

### 6.10 Person Re-ID & Attribute Engine
- **File**: `backend/ai/person/person_reid.py`, `backend/ai/person/person_attribute_engine.py`
- **Embedding**: MobileNetV3 feature extraction (768-dimensional `person_crop` vector space in Qdrant)
- **Attribute Analysis**: Extracts upper/lower clothing color, gender classification, posture/action, and backpack/handbag detection.
- **Cross-Camera Tracking**: Computes cosine similarity across distinct camera feeds for re-identifying individuals.

### 6.11 Downstream Task Router
- **File**: `backend/ai/routing/downstream_router.py`
- **Purpose**: Dynamic task dispatcher managing load balancing between real-time YOLO detection frames and heavy multimodal VLM tasks (Florence-2 / Moondream).

## 7. API Reference

All routes mounted under `/api/v1` (`main.py:190-206`). Authorization is JWT Bearer unless noted.

### 7.1 Authentication `/api/v1/auth`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | None | OAuth2 password form -> JWT, role, `must_change_password` |
| POST | `/auth/register` | admin | Create user. All new accounts: `must_change_password=True` |
| POST | `/auth/change-password` | any | Change own password |

Default seeded accounts (`auth/router.py:244-259`):
| Username | Password | Role |
|---|---|---|
| admin | Admin@123456 (or INITIAL_ADMIN_PASSWORD) | admin |
| operator | Operator@123456 | operator |
| viewer | Viewer@123456 | viewer |

Rate limit: 10 fails / 5-min window -> 15-min lockout (HTTP 429 + Retry-After) (`auth/router.py:25-27`).

### 7.2 Cameras `/api/v1/cameras`
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/cameras` | viewer | List cameras with telemetry, HLS/WebRTC URLs |
| POST | `/cameras` | operator | Add camera; spawns Recorder + AIWorker |
| PUT | `/cameras/{id}` | operator | Update camera; restarts workers on URL change |
| DELETE | `/cameras/{id}` | operator | Delete; stops workers; cascades zones/alerts |
| POST | `/cameras/scan` | viewer | WS-Discovery UDP for ONVIF cameras |
| POST | `/cameras/resolve-onvif` | viewer | Resolve RTSP URI via ONVIF SOAP |
| GET | `/cameras/{id}/zones` | viewer | Zone polygon definitions |
| POST | `/cameras/{id}/zones` | admin | Save/replace zone polygons |
| GET | `/cameras/{id}/stream` | viewer | Resolve streaming URL (HLS/WebRTC/MJPEG) |
| GET | `/cameras/{id}/mjpeg` | None | Async MJPEG stream (~25fps) |

Geocoding (`cameras.py:26`): hardcoded Surat landmarks first, then Nominatim OSM (1.5s timeout).
HLS URL pattern: `http://localhost:8888/{camera_id}/index.m3u8` (`cameras.py:99`)
WebRTC URL pattern: `http://localhost:8889/{camera_id}/whep` (`cameras.py:100`)

### 7.3 Alerts & Playback
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/alerts` | viewer | Last 100 alerts (timestamp desc) |
| POST | `/alerts/{id}/acknowledge` | operator | Mark acknowledged |
| GET | `/alerts/{id}/export` | operator | SHA-256 evidence ZIP download |
| GET | `/playback/snapshot/{snap_id}` | viewer | JPEG snapshot; SVG placeholder if missing |
| GET | `/playback/video/{cam}/{file}` | viewer | MP4 recording segment |

### 7.4 Analytics
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/monitor/health` | viewer | CPU/RAM/GPU/DB/Qdrant health |
| GET | `/ai/status` | viewer | YOLO/OCR/Embedder/Florence load state |
| GET | `/camera-telemetry` | viewer | Per-camera FPS, person count |
| GET | `/analytics/heatmap?camera_id=` | viewer | Normalized (x,y,value) heatmap |
| GET | `/analytics/traffic-speed?camera_id=` | viewer | Speed/flow analytics |
| GET | `/forensics/video-qa?question=` | viewer | NL query answered from DB records |

### 7.5 Records
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/records/stats` | viewer | Counts: faces, vehicles, plates, OCR, captions, identities |
| GET | `/records/faces` | viewer | Face sightings grouped by label |
| GET | `/records/vehicles` | viewer | Vehicle ledger |
| GET | `/records/plates` | viewer | License plate records |
| GET | `/records/captions` | viewer | Scene caption records |
| GET | `/records/ocr` | viewer | Raw OCR records |
| GET | `/florence/stats` | None | Florence queue stats |

### 7.6 Search
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/search/semantic?q=` | viewer | Vector similarity search |
| GET | `/search/license-plate?q=` | viewer | SQL LIKE search |
| POST | `/search/face` | viewer | Image upload -> face cosine search |
| GET | `/search/debug` | viewer | Vector DB size, demo_mode, Qdrant |

### 7.7 Forensics
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/forensics/exports` | viewer | Export ledger (from AuditLog) |
| DELETE | `/forensics/exports/clear` | operator | Purge ledger entries |
| POST | `/forensics/export?camera_id=&start_time=&end_time=` | operator | FFmpeg evidence ZIP + SHA-256 |
| GET | `/forensics/download/{filename}` | viewer | Download ZIP (safe_join_path enforced) |
| GET | `/forensics/fir-report/{export_id}` | operator | HTML FIR Annexure + SHA-256 case hash |
| GET | `/forensics/trajectory/{subject_id}` | viewer | Cross-camera trajectory map |
| GET | `/forensics/co-occurrence?camera_id=` | viewer | Spatial-temporal co-occurrence groups |

Evidence ZIP contents (`event_export.py:14-19`):
1. `evidence_clip.mp4` -- keyframe-aligned clip (nearest segment, 15-min tolerance)
2. `trigger_frame.jpg` -- alert snapshot
3. `metadata.json` -- full provenance metadata
4. `signature.sha256` -- SHA-256 of the video clip
5. `chain_of_custody.txt` -- action log

### 7.8 Watchlist
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/watchlist` | viewer | All POIs with DPDP retention status |
| POST | `/watchlist` | operator | Register POI with face photo |
| POST | `/watchlist/purge-expired` | admin | Delete POIs >90 days (DPDP) |
| GET | `/watchlist/{uuid}/snapshot` | viewer | POI face crop JPEG |

DPDP status labels (`watchlist.py:36-39`):
- <75 days: `ACTIVE_RETENTION_VERIFIED`
- 75-90 days: `APPROACHING_RETENTION_LIMIT`
- >90 days: `RETENTION_EXCEEDED_PURGE_REQUIRED`

### 7.9 Admin
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/admin/users` | admin | List all users (optional: include soft-deleted) |
| POST | `/admin/users` | admin | Create user with role + camera ACL |
| PUT | `/admin/users/{id}` | admin | Update role/status/password/ACL |
| DELETE | `/admin/users/{id}` | admin | Soft-delete (sets deleted_at) |
| POST | `/admin/users/{id}/hard-delete` | admin | Hard delete (admin password re-auth) |
| GET | `/admin/audit-log` | admin | Paginated audit log with filters |

### 7.10 Custom Alert Rules
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/rules` | viewer | List rules |
| POST | `/rules` | operator | Create rule (prompt, camera_id, severity, confidence) |
| PUT | `/rules/{id}/toggle` | operator | Enable/disable |
| DELETE | `/rules/{id}` | operator | Delete |

### 7.11 E-Challan
| Method | Path | Min Role | Description |
|---|---|---|---|
| GET | `/challan/generate/{alert_id}` | operator | HTML citation with QR + SHA-256 |

### 7.12 Infrastructure
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/healthz` | None | Kubernetes liveness probe |
| GET | `/readyz` | None | Readiness probe (checks PostgreSQL) |
| GET | `/metrics` | None | Prometheus text metrics |
| WS | `/api/v1/ws/alerts` | None | WebSocket alert push |
| POST | `/api/v1/bwc/live/register` | None | Register BWC live stream |

---

## 8. Database Schema

Defined in `backend/database/models.py`. PostgreSQL 15 (SQLite in local dev fallback).
Created via `Base.metadata.create_all()` at lifespan startup (`main.py:69`).

### `cameras`
| Column | Type | Default | Notes |
|---|---|---|---|
| id | String PK | -- | e.g. `cam_1` |
| name | String | -- | Display name |
| location | String | -- | Location string |
| stream_url | String | -- | RTSP / file / YouTube URL |
| status | String | connecting | `connecting/online/offline` |
| width | Integer | 1920 | Frame width |
| height | Integer | 1080 | Frame height |
| latitude | Float | 21.1702 | GPS lat (Surat default) |
| longitude | Float | 72.8311 | GPS lon |

### `alert_configs`
| Column | Type | Default | Notes |
|---|---|---|---|
| id | Integer PK | -- | |
| camera_id | String FK | -- | -> cameras |
| loitering_seconds | Float | 10 | Loitering threshold |
| running_speed_threshold | Float | 150.0 | px/s |
| crowd_density_threshold | Integer | 5 | person count |

### `zones`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String FK | -> cameras |
| type | String | restricted/loitering/crowd/wrong_direction/line_cross |
| name | String | Display name |
| points | Text | JSON [[x,y],...] normalized 0-1 |
| direction_vector | Text | JSON [dx,dy] for directional zones |

### `alerts`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String FK | -> cameras |
| alert_type | String | loitering/running/crowd/restricted/... |
| message | Text | Human-readable |
| severity | String | low/medium/high/critical |
| timestamp | DateTime | IST |
| snapshot_url | String | JPEG path |
| video_url | String | MP4 clip path |
| is_acknowledged | Boolean | Operator ACK flag |
| track_uuid | String | Associated track |

### `tracks`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String FK | |
| track_id | Integer | ByteTrack local ID |
| track_uuid | String | `TRK_{camera_id}_{track_id}` |
| label | String | COCO class name |
| first_seen | DateTime | |
| last_seen | DateTime | |
| speed | Float | EMA px/s |
| path_history | Text | JSON [[cx,cy],...] last 30 |
| last_bbox_x | Float | Normalized center X |
| last_bbox_y | Float | Normalized center Y |

### `faces`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String | |
| track_uuid | String FK | -> tracks |
| label | String | identity_uuid or POI_UNKNOWN |
| embedding_id | String | Qdrant / snapshot UUID |
| confidence | Float | SFace cosine score |
| timestamp | DateTime | |

### `vehicles`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String | |
| track_uuid | String FK | -> tracks |
| vehicle_type | String | COCO class |
| vehicle_color | String | HSV dominant color |
| license_plate | String | OCR text |
| ocr_confidence | Float | |
| snapshot_url | String | JPEG path |
| bbox | Text | JSON [x1,y1,x2,y2] |
| timestamp | DateTime | |

### `scene_captions`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String | |
| caption | Text | Florence-2 or Moondream text |
| snapshot_url | String | Frame image path |
| timestamp | DateTime | |

### `raw_ocr_records`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| camera_id | String | |
| track_uuid | String | |
| detected_text | String | Post-processed |
| raw_text | String | Unprocessed OCR output |
| ocr_confidence | Float | |
| source_type | String | license_plate / sign / etc. |
| snapshot_url | String | |
| timestamp | DateTime | |

### `global_identities`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| identity_uuid | String | Globally unique UUID |
| name | String | POI display name |
| type | String | person / vehicle |
| first_seen | DateTime | DPDP retention start |
| last_seen | DateTime | |
| embedding_id | String | Qdrant vector ID |
| snapshot_path | Text | Face crop path |

### `users`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| username | String unique | |
| password_hash | String | bcrypt |
| role | String | admin/operator/viewer |
| status | String | active/suspended |
| must_change_password | Boolean | Force change on login |
| allowed_cameras | Text | JSON list of camera IDs |
| deleted_at | DateTime | Soft-delete timestamp |

### `audit_logs`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| action | String | LOGIN_SUCCESS/EVIDENCE_EXPORT/... |
| detail | Text | Context (pipe-delimited for exports) |
| username | String | |
| ip_address | String | X-Forwarded-For or direct |
| timestamp | DateTime | |

### `custom_alert_rules`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| name | String | Display name |
| prompt | Text | NLP prompt or plate/class pattern |
| camera_id | String | ALL or specific camera ID |
| severity | String | low/medium/high |
| is_active | Boolean | |
| confidence_threshold | Float | Min cosine sim (default 0.65) |
| created_at | DateTime | |

### `search_history`
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| username | String | Querying user |
| query_text | String | Natural language or license plate query |
| query_type | String | `semantic` / `face` / `license_plate` |
| result_count | Integer | Number of matched items |
| timestamp | DateTime | Search execution time |

---

## 9. Configuration Files

### `configs/models.json`
Read by `backend/config/service.py`:
```json
{
  "demo_mode": false,
  "yolo": {
    "model_path": "yolo26l.pt",
    "device": "cuda",
    "conf": 0.35
  },
  "vehicle": {
    "device": "cuda",
    "ocr_engine": "paddleocr"
  },
  "face": {
    "device": "cuda"
  },
  "florence": {
    "model_id": "microsoft/Florence-2-base",
    "device": "cuda",
    "dispatch_interval_seconds": 0.5,
    "max_new_tokens": 1024,
    "caption_batch_size": 2
  },
  "moondream": {
    "enabled": true,
    "invoke_every_n_frames": 30,
    "dispatch_interval_seconds": 0.5
  }
}
```
`demo_mode: true` -> MockYOLO, MockOCR, MockFlorence stubs.

### `configs/cameras.json`
Seeded into DB at startup if table is empty (`main.py:83-96`):
```json
[{"id": "cam_1", "name": "...", "stream_url": "rtsp://...", "width": 1920, "height": 1080}]
```

### `configs/alerts.json`
Per-camera behavior thresholds loaded by AI worker:
```json
{
  "cooldown_seconds": 30.0,
  "loitering": {"enabled": true, "time_threshold_seconds": 10.0},
  "running": {"enabled": true, "speed_threshold_pixels_per_second": 150.0},
  "crowd": {"enabled": true, "density_threshold": 5},
  "restricted": {"enabled": true},
  "wrong_direction": {"enabled": false},
  "abandoned": {"enabled": false}
}
```

### `configs/zones.json`
Zone polygons (normalized 0-1 coords):
```json
[{"camera_id": "cam_1", "type": "restricted", "name": "Zone", "points": [[0.1,0.2],[0.5,0.8]]}]
```

### `configs/privacy.json`
Global privacy redaction (`ai/privacy/redactor.py:15`):
```json
{"enabled": false, "redact_faces": true, "redact_plates": true, "blur_kernel_size": 51}
```

---

## 10. Environment Variables

From `.env.example`:

| Variable | Default | Description |
|---|---|---|
| DATABASE_URL | postgresql://vms_user:vms_password@localhost:5432/vms_db | SQLAlchemy DSN |
| SECRET_KEY | (placeholder) | JWT HS256 signing key |
| ALGORITHM | HS256 | JWT algorithm |
| ACCESS_TOKEN_EXPIRE_MINUTES | 480 | 8-hour JWT lifetime |
| APP_ENV | development | `production` enforces strict CORS + Kafka |
| CORS_ALLOWED_ORIGINS | * | Comma-separated origins; must not be * in production |
| KAFKA_BOOTSTRAP_SERVERS | localhost:9092 | Kafka broker |
| USE_MEMORY_BUS_ONLY | false | Skip Kafka, use in-memory bus (`kafka_client.py:30`) |
| QDRANT_HOST | localhost | Qdrant host |
| QDRANT_PORT | 6333 | Qdrant port |
| MINIO_ENDPOINT | localhost:9000 | MinIO S3 endpoint |
| MINIO_ROOT_USER | minio_admin | MinIO access key |
| MINIO_ROOT_PASSWORD | minio_password | MinIO secret |
| MINIO_SECURE | false | HTTPS for MinIO |
| INITIAL_ADMIN_PASSWORD | Admin@123456 | Default admin password (`auth/router.py:242`) |
| MOONDREAM_API_KEY | (empty) | Single Moondream API key |
| MOONDREAM_API_KEYS | (empty) | Comma-separated key pool for round-robin |
| MOONDREAM_MODEL | moondream3.1-9B-A2B | Moondream model name |

---

## 11. Key Features

### Behavior Detection Subsystem
Independent detector classes in `backend/ai/behavior/`:

| Behavior | Severity | Key Threshold |
|---|---|---|
| Restricted Area | high | Point-in-polygon (zone type=restricted) |
| Loitering | medium | Time-in-zone >= `loitering.time_threshold_seconds` (default 10s) |
| Running | low | Speed >= `running.speed_threshold_pixels_per_second` (default 150 px/s) |
| Crowd Density | medium | Person count in zone >= `crowd.density_threshold` (default 5) |
| Wrong Direction | high | Track velocity dot product vs zone direction_vector |
| Abandoned Object | high | Object stationary without nearby person for threshold duration |

Alert deduplication: `_should_emit_alert()` (`behavior_engine.py:20-37`), sliding cooldown per
(track_id, alert_type, sub_key), default 30s. History pruned when >500 entries.

### Custom Rule Engine
`CustomRuleEvaluator` (`custom_rules.py`) supports:
1. License plate matching: exact or wildcard (MH87*)
2. Object class keyword: detected COCO class names (weapon, knife, fire, crowd)
3. Semantic NL matching: SentenceTransformer embed(prompt) vs scene caption embedding; cosine >= confidence_threshold

Rule prompt embeddings cached in `_rule_embedding_cache`.

### Forensic Evidence Export
Evidence ZIPs (`event_export.py:14-19`):
- Keyframe-aligned FFmpeg clip from recording nearest to alert (15-min tolerance)
- trigger_frame.jpg + metadata.json + signature.sha256 + chain_of_custody.txt
- SHA-256 computed via streaming 64KB reads (`event_export.py:47-52`)

### FIR Report Generation (`fir_report.py`)
- HTML FIR Evidence Annexure at `/api/v1/forensics/fir-report/{export_id}`
- SHA-256 over: `case_num|username|timestamp_iso|audit#{audit_id}` (`fir_report.py:33-41`)
- XSS protection: export_id validated against `^[A-Za-z0-9_-]{1,64}$` (`fir_report.py:60`)
- operator+ role required (COMP-04 fix, `fir_report.py:47`)

### E-Challan Citation (`challan.py`)
- Inline base64 QR code via `qrcode` library (`challan.py:27-40`)
- Vehicle DB lookup for license plate details
- SHA-256 integrity signature
- operator+ required

### Multi-Camera Face Identity Merging
`GlobalIdentityManager.get_or_create_face_identity()` (`identity.py:16`):
1. L2-normalize face embedding
2. Query Qdrant `vms_embeddings` collection using `face` named vector (2s timeout)
3. Fallback: scan `model_manager.vector_db` in-memory list
4. Threshold: cosine >= 0.40 (SFace calibrated)
5. Match: update `last_seen` in `global_identities`
6. No match: create new GlobalIdentity + Face rows

### DPDP Compliance
- 3-tier retention status tracking in `/watchlist` responses (`watchlist.py:36-39`)
- Admin-only `POST /watchlist/purge-expired` bulk-deletes expired entries
- Every purge logged to `audit_logs` with username + IP

### Stream Connection Resilience
`CameraStream._capture_loop()` (`stream_manager.py:163`):
- Exponential backoff: 2s -> doubles -> 60s cap
- 50 consecutive frame failures trigger reconnect
- Sub-stream failover (101->102, main->sub, subtype=0->subtype=1)
- Reference counting: stream only stopped when all consumers released

### Body-Worn Camera Integration
- `POST /api/v1/bwc/live/register` registers cellular BWC stream (`main.py:232-249`)
- `bwc_live_ingest.py` ingests BWC alongside CCTV feeds

### Health Monitoring
`GET /monitor/health` via `monitoring/health.py`:
- CPU/RAM/Disk: psutil
- GPU: pynvml -> torch.cuda -> GPU_UNAVAILABLE
- PostgreSQL: SQLAlchemy ping
- Qdrant: HTTP status check
- Per-camera worker status

---

## 12. Infrastructure / Docker

### docker-compose.yml Services
| Service | Image | Ports | Volumes |
|---|---|---|---|
| postgres | postgres:15 | 5432 | postgres_data:/var/lib/postgresql/data |
| qdrant | qdrant/qdrant:latest | 6333, 6334 | qdrant_data:/qdrant/storage |
| mediamtx | bluenviron/mediamtx | 8554, 8888, 8889 | config volume |
| minio | minio/minio:latest | 9000, 9001 | minio_data:/data |
| zookeeper | confluentinc/cp-zookeeper:7.6.0 | 2181 | ephemeral |
| kafka | confluentinc/cp-kafka:7.6.0 | 9092 | ephemeral |

MediaMTX re-publishes all RTSP streams as:
- HLS: `http://localhost:8888/{camera_id}/index.m3u8`
- WebRTC (WHEP): `http://localhost:8889/{camera_id}/whep`

### NVR Emulator
`backend/scripts/nvr_emulator.py`: loops local MP4 files into RTSP via FFmpeg for offline dev.
Started by `manage.ps1:121`.

### Production Docker Container Strategy

#### Backend Image (`Dockerfile.backend`)
Multi-stage build leveraging `python:3.10-slim`:
- Installs system packages required by OpenCV and FFmpeg (`libgl1`, `libglib2.0-0`, `ffmpeg`, `libpq-dev`).
- Installs Python dependencies from `requirements.txt`.
- Copies backend, config, storage, and Alembic files.
- Exposes port 8000 and runs Uvicorn ASGI server.

#### Frontend Image (`Dockerfile.frontend`)
Multi-stage build leveraging `node:20-alpine` and `nginx:alpine`:
- **Stage 1 (Build)**: Installs dependencies via `npm ci`, builds production bundles via `vite build` to `/app/dist`.
- **Stage 2 (Nginx)**: Serves static dist files and provides reverse proxy routes:
  - `/` -> static SPA index.html fallback
  - `/api/` -> proxies to `http://backend:8000/api/` with header preservation
  - `/ws/` -> WebSocket connection upgrade proxying to `http://backend:8000/ws/`

---

## 13. Setup & Running Locally

### Automated Testing Suite
The repository includes comprehensive automated unit, integration, stress, and security tests under `tests/` and `backend/tests/`.

Run full test suite:
```bash
.venv\Scripts\python.exe -m pytest
```

Run specific test sub-suites:
```bash
.venv\Scripts\python.exe -m pytest tests/test_security_phase1.py
.venv\Scripts\python.exe -m pytest backend/tests/test_ssrf_proxy.py
```

### Data Reset & Purge Utility
To perform a complete wipe and fresh state reset across database tables, Qdrant vector collections, snapshots, and video recordings:

```bash
.venv\Scripts\python.exe reset_vms_data.py
```

---

### Prerequisites
- Python 3.10+ (venv at `.venv/`)
- Node.js 18+
- Docker Desktop
- FFmpeg on PATH
- NVIDIA GPU + CUDA drivers (optional, required for real-time GPU inference)

### Windows (manage.ps1)
```powershell
.\manage.ps1 start    # Start all services
.\manage.ps1 stop     # Stop all services
.\manage.ps1 restart  # Restart all services
```

`manage.ps1 start` (`manage.ps1:73-154`):
1. Creates `logs/` and `storage/` directories
2. `docker compose up -d postgres qdrant mediamtx minio zookeeper kafka`
3. Seeds cameras via `backend/scripts/seed_rtsp_cams.py`
4. Starts Uvicorn: `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log`
5. Starts Vite: `npm run dev` (from frontend/)
6. Starts NVR Emulator
7. Polls `/docs` for readiness (up to 80s)

### Access Points
| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Qdrant UI | http://localhost:6333/dashboard |
| MinIO Console | http://localhost:9001 |
| HLS streams | http://localhost:8888/{cam_id}/index.m3u8 |

### Manual Start
```bash
# Backend
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm run dev

# Database migrations
.venv\Scripts\python.exe -m alembic upgrade head
```

---

## 14. Security Model

### JWT
- Algorithm: HS256, key: `SECRET_KEY` env var
- Lifetime: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 8 hours)
- `must_change_password` flag enforced by frontend before allowing navigation

### RBAC
- **viewer**: all GET endpoints
- **operator**: viewer + camera management, alert ACK, evidence export, watchlist CRUD
- **admin**: operator + user management, hard-delete, zone admin, DPDP purge

### Rate Limiting (SEC-01)
- In-memory per-IP (`auth/router.py:23-64`)
- 10 fails / 5-min window -> 15-min lockout
- HTTP 429 with `Retry-After` header

### SSRF Protection (SEC-05)
`backend/utils/ssrf.py:validate_proxy_url()`:
- Blocks: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, ::1, fe80::/10, fc00::/7, multicast
- Blocks internal TLDs: .local, .internal, .lan, .home.arpa, .invalid
- Resolves all A/AAAA records, checks none are private (DNS rebinding defense)
- Only http/https schemes allowed

### Path Traversal
`backend/utils/security.py:safe_join_path()` validates resolved path is within expected base dir.

### Audit Logging
All privileged actions -> `audit_logs` via `log_audit_event()` (`utils/audit.py`):
- LOGIN_SUCCESS/LOGIN_FAILED/LOGIN_BLOCKED
- USER_REGISTER/PASSWORD_CHANGED
- EVIDENCE_EXPORT
- DPDP_PURGE

### CORS
- Development: * (permissive)
- Production: `APP_ENV=production` requires non-wildcard `CORS_ALLOWED_ORIGINS` or raises RuntimeError (`main.py:174-177`)

### Privacy Redaction
Gaussian blur (kernel 51) on face and plate bbox regions (`ai/privacy/redactor.py`).
Controlled by `configs/privacy.json` (global) and per-request override for exports.

---

## 15. Known Issues / Limitations

### Architecture
1. **In-memory rate limiter** (`auth/router.py`): process-local, not shared across Uvicorn workers. Redis required for multi-process horizontal scaling.
2. **In-process WebSocket list** (`main.py:44`): not shared across workers. Redis pub/sub or Kafka consumer required for multi-process WebSocket push.
3. **Kafka fallback is silent**: in non-production mode, Kafka failures silently use MemoryEventBus (`kafka_client.py:52`). No alerting on event loss.
4. **ByteTrack IDs reset on reconnect**: stream reconnect reinitializes ByteTrack; track IDs restart from 0, creating duplicate track records.
5. **Single GPU lock**: `model_manager.gpu_lock` serializes all CUDA calls globally. With many cameras this bottlenecks throughput even with batch scheduling.

### Data / AI
6. **florence flash_attn mock** (`model_manager.py:208-231`): MagicMock workaround may fail silently on transformer versions that changed internal import paths.
7. **Hardcoded Surat coordinates**: Geocoding landmarks in `cameras.py:36-57` and trajectory GPS in `trajectory.py:12-22` are specific to Surat. Non-Surat deployments will produce wrong map positions.
8. **Acoustic detection not wired**: `acoustic_engine.py` implements the FFT classifier but there is no PCM audio capture loop integrated with the RTSP pipeline. Audio alerts are not emitted at runtime.
9. **Vector DB list race** (`model_manager.vector_db`): plain Python list appended from multiple threads without a lock. Can cause `RuntimeError: list changed size during iteration` in high-camera-count deployments.
10. **OCR confidence default**: `records.py:193` returns 0.90 as OCR confidence when the real value is None, masking poor OCR quality in reporting.

### Security
11. **No JWT revocation**: no token blacklist or refresh tokens. Compromised tokens are valid until expiry (up to 8 hours).
12. **Hard-delete re-auth**: `admin/router.py` re-authenticates admin_password via DB, but a compromised admin session can still perform hard-deletes.

### Operations
13. **Windows-only management script**: `manage.ps1` is PowerShell. No `manage.sh` equivalent for Linux/macOS production deployments.
14. **No log rotation**: `logs/backend.log` grows unbounded during long-running deployments.
15. **DELETE in GET handler**: `records.py:59` executes a row DELETE inside a GET handler, which is non-idiomatic and breaks read-replica compatibility.

---

## 16. Dependency Index

### Python (`requirements.txt`)
| Package | Purpose |
|---|---|
| fastapi | Web framework |
| uvicorn | ASGI server |
| sqlalchemy | ORM |
| alembic | Database migrations |
| psycopg2-binary | PostgreSQL adapter |
| python-jose[cryptography] | JWT |
| passlib[bcrypt] | Password hashing |
| ultralytics | YOLO + ByteTrack |
| torch / torchvision | GPU tensors, MobileNetV3 |
| transformers | Florence-2 (HuggingFace) |
| sentence-transformers | BAAI/bge-large-en-v1.5 |
| opencv-python-headless | Frame capture, face models |
| paddlepaddle / paddleocr | License plate OCR (primary) |
| easyocr | License plate OCR (fallback) |
| qdrant-client | Vector DB client |
| kafka-python | Kafka producer |
| boto3 | MinIO S3 client |
| httpx | Async HTTP (Moondream API) |
| yt-dlp | YouTube live stream resolution |
| slowapi | Rate limiting framework layer |
| pytest | Automated test framework |
| psutil | System vitals |
| pynvml | NVIDIA GPU stats |
| qrcode[pil] | QR code for E-Challan |
| Pillow | Image I/O |
| numpy | Numerical operations |
| defusedxml | Safe XML parsing (ONVIF) |
| python-dotenv | .env loading |
| python-multipart | File upload parsing |

### Node.js (`frontend/package.json`)
| Package | Purpose |
|---|---|
| react + react-dom | UI framework (v19) |
| @mui/material + @mui/icons-material | MUI components |
| lucide-react | UI Icon sets |
| hls.js | HTML5 HLS video player library |
| recharts | Telemetry and performance charts |
| react-router-dom | Routing (v7) |
| @emotion/react + @emotion/styled | MUI styling |
| vite | Build tool + dev server |
| @vitejs/plugin-react | Vite React plugin |
| oxlint | Linter |
| playwright | End-to-end testing |

---

*Documentation generated by line-by-line source audit of every file in the repository -- August 2026.*
*All claims are traceable to specific source files and line numbers cited inline.*
