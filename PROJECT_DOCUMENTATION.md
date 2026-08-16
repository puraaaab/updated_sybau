# PROJECT_DOCUMENTATION.md
> **Ground-truth, comprehensive technical audit and master architecture documentation for the Sybau AI Video Management System (VMS Pro / PS-11).**
> Every specification is verified and traceable to active source code.

---

## TABLE OF CONTENTS
1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Technology Stack](#3-technology-stack)
4. [System Architecture & Master Topology](#4-system-architecture--master-topology)
   - [4.1 Master System Topology & Component Interconnect](#41-master-system-topology--component-interconnect)
   - [4.2 Concurrency Model & Multithreading Architecture](#42-concurrency-model--multithreading-architecture)
   - [4.3 Multi-Tenancy & Tenant Data Segregation](#43-multi-tenancy--tenant-data-segregation)
5. [Data Flow & Pipeline Stages](#5-data-flow--pipeline-stages)
   - [5.1 Frame Ingestion & 4-Tier Hardware Decoder Cascade](#51-frame-ingestion--4-tier-hardware-decoder-cascade)
   - [5.2 GPU Scheduling & Micro-Batching Pipeline](#52-gpu-scheduling--micro-batching-pipeline)
   - [5.3 Downstream Dual-Path Router & Load Shedding](#53-downstream-dual-path-router--load-shedding)
   - [5.4 Multi-Space Vector Indexing & Semantic Search](#54-multi-space-vector-indexing--semantic-search)
   - [5.5 Conversational AI Copilot & Multilingual Reasoning](#55-conversational-ai-copilot--multilingual-reasoning)
   - [5.6 Camera Topology & Predictive Next-Hop Escape Routing](#56-camera-topology--predictive-next-hop-escape-routing)
   - [5.7 Dynamic Privilege Elevation Workflow](#57-dynamic-privilege-elevation-workflow)
   - [5.8 Multimodal Event Fusion & Canonical Ledger](#58-multimodal-event-fusion--canonical-ledger)
   - [5.9 Forensics, Evidence Export & Chain of Custody](#59-forensics-evidence-export--chain-of-custody)
   - [5.10 Law Enforcement Watchlist & DPDP Purge Pipeline](#510-law-enforcement-watchlist--dpdp-purge-pipeline)
6. [AI / ML Models & Perception Engines](#6-ai--ml-models--perception-engines)
   - [6.0 Master End-to-End AI Orchestrator Flowchart](#60-master-end-to-end-ai-orchestrator-flowchart)
   - [6.1 Model Specifications & Pipeline Details](#61-model-specifications--pipeline-details)
7. [API Reference (All 18+ Routers)](#7-api-reference-all-18-routers)
8. [Database Schema (All 36 Models)](#8-database-schema-all-36-models)
9. [Configuration Files & System Settings](#9-configuration-files--system-settings)
10. [Environment Variables Catalog](#10-environment-variables-catalog)
11. [Master Feature Inventory (47 Features)](#11-master-feature-inventory-47-features)
12. [Infrastructure & Container Deployment](#12-infrastructure--container-deployment)
13. [Setup & Running Locally](#13-setup--running-locally)
14. [Security Architecture & DPDP Compliance](#14-security-architecture--dpdp-compliance)
15. [Known Limitations & Engineering Roadmap](#15-known-limitations--engineering-roadmap)
16. [Dependency Index](#16-dependency-index)
17. [Unique Selling Points (USPs) & Architectural Differentiators](#17-unique-selling-points-usps--architectural-differentiators)

---

## 1. Project Overview

**Sybau VMS Pro (PS-11)** is a real-time, GPU-accelerated AI video management and forensic investigation platform designed for high-density smart city surveillance deployments (calibrated for Surat, Gujarat, India).

Key capabilities:
- **Multi-Protocol Stream Ingestion**: Real-time monitoring across RTSP, HLS, WebRTC/WHEP, YouTube, Body-Worn Cameras (BWC), and local NVR loops with sub-stream auto-failover.
- **Micro-Batched GPU Acceleration**: Dynamic 15ms priority queue micro-batching under unified `gpu_lock` eliminating VRAM deadlocks.
- **Multimodal AI Perception**: YOLO object detection, ByteTrack tracking, YuNet+SFace facial biometrics, MobileNetV3 Re-ID, PaddleOCR/EasyOCR license plate extraction, Florence-2 and Moondream 3.1 vision-language captioning, and 16kHz PCM acoustic DSP anomaly detection.
- **Conversational AI Investigation Copilot & Chatbot**: Natural language multi-turn investigation in English, Hindi, and Gujarati with visual citations, trajectory timeline playback, and 18 controlled tool interfaces.
- **Camera Topology & Predictive Next-Hop Escape Routing**: Interactive 2D topological network canvas with kinematic suspect escape forecasting and downstream interception alerts.
- **Dynamic Role Privilege Elevation (FEAT-02)**: Time-to-Live (TTL) temporary role promotion with strict admin approval, self-approval prevention, and dynamic in-memory authorization.
- **AI Skill Registry & Declarative Event Rules (FEAT-03)**: Dynamic skill registration, per-camera allocation, and multi-condition compound event fusion.
- **Law Enforcement Watchlists & CCTNS Integration**: Automated cross-referencing against State Police CCTNS stolen vehicles and wanted persons/missing children dossiers.
- **Court-Admissible Forensic Evidence**: SHA-256 signed evidence ZIP packages, chain-of-custody logs, HTML FIR annexures under Indian Evidence Act Section 65B / BSA, and E-Challan citations with QR codes.
- **DPDP Act 2023 Compliance**: 3-tier retention status tracking and automated 90-day biometric data purging.

---

## 2. Repository Structure

```
sybau_granth/
├── backend/
│   ├── main.py                          # Application entry point, lifespan, router mounts, WebSocket gateway
│   ├── admin/
│   │   └── router.py                    # User management, RBAC, paginated audit logs
│   ├── ai/
│   │   ├── model_manager.py             # Singleton deep learning model manager (YOLO, OCR, Florence, Embedder)
│   │   ├── scheduler.py                 # Priority micro-batching InferenceScheduler
│   │   ├── audio/
│   │   │   └── acoustic_engine.py       # 16kHz PCM FFT/RMS acoustic intelligence & anomaly engine
│   │   ├── behavior/
│   │   │   ├── adaptive_baseline.py     # Hourly statistical occupancy tracking & z-score anomaly detector
│   │   │   ├── behavior_engine.py       # BehaviorEngine orchestrator for live alerts
│   │   │   ├── custom_rules.py          # NLP semantic rule evaluator & plate wildcards
│   │   │   ├── spatial_analytics.py     # Line crossing, tailgating, fall detection, PPE, queue, parking
│   │   │   ├── crowd.py                 # Crowd density threshold detector
│   │   │   ├── loitering.py             # Loitering dwell time threshold detector
│   │   │   ├── restricted.py            # Point-in-polygon restricted area geofence
│   │   │   ├── running.py               # Speed-based rapid movement detector
│   │   │   └── wrong_direction.py       # Vector dot product direction checker
│   │   ├── captioning/
│   │   │   ├── caption_integrity.py     # SHA-256 image-to-caption cryptographic binding
│   │   │   ├── captioner.py             # Florence-2 round-robin scheduler & Windows flash-attn patch
│   │   │   └── moondream_captioner.py   # Moondream 3.1 cloud API key pool round-robin worker
│   │   ├── detection/
│   │   │   ├── batch_collector.py       # DeadlinedBatchCollector GPU throttle
│   │   │   └── yolo.py                  # YOLO detect_and_track wrapper with COCO class filtering
│   │   ├── embeddings/
│   │   │   └── embedder.py              # SentenceTransformer BAAI/bge-large-en-v1.5 dense embedder
│   │   ├── face/
│   │   │   └── face_pipeline.py         # YuNet ONNX detection + SFace ONNX 128d face recognition
│   │   ├── person/
│   │   │   ├── person_attribute_engine.py # HSV clothing color, gender, posture & bag classifier
│   │   │   ├── person_reid.py           # MobileNetV3 768d Person Re-ID embedding generator
│   │   │   └── reid_pipeline.py         # Person Re-ID matching pipeline
│   │   ├── pipeline/
│   │   │   ├── frame_governor.py        # Adaptive frame rate governor
│   │   │   ├── orchestrator.py          # Per-frame multimodal AI pipeline orchestrator
│   │   │   └── yolo_gate.py             # Ingestion gating interface
│   │   ├── privacy/
│   │   │   ├── privacy_engine.py        # 6-mode privacy redaction controller
│   │   │   └── redactor.py              # Gaussian blur face & plate redaction engine
│   │   ├── routing/
│   │   │   └── downstream_router.py     # Zero-latency Path A vs Async Path B router with load shedding
│   │   ├── skills/
│   │   │   └── skill_registry.py        # In-memory skill registry controller
│   │   ├── tracking/
│   │   │   └── tracker.py               # TrajectoryTracker with EMA velocity & 30-centroid path history
│   │   ├── vehicle/
│   │   │   ├── alpr_engine.py           # License plate recognition pipeline
│   │   │   ├── plate_parser.py          # Indian license plate normalization & regex parser
│   │   │   └── vehicle_reid.py          # MobileNetV3 576d Re-ID + HSV plate localization
│   │   └── workers/
│   │       └── secondary_consumers.py   # Async background vector indexing & heavy worker consumer
│   ├── auth/
│   │   ├── helpers.py                   # JWT creation, dynamic TTL elevation authorization, password hash
│   │   └── router.py                    # Login, user registration, password change endpoints
│   ├── config/
│   │   └── service.py                   # JSON configuration loader service
│   ├── database/
│   │   ├── connection.py                # SQLAlchemy engine, SessionLocal, Base
│   │   ├── models.py                    # 36 SQLAlchemy ORM models & table definitions
│   │   └── migrations/                  # Automated versioned migration scripts (001 to 008)
│   │       ├── 001_multi_tenancy_and_user_columns.py
│   │       ├── 002_phase4_compound_indexes.py
│   │       ├── 003_event_rules_and_skill_registry.py
│   │       ├── 004_privilege_elevation_workflow.py
│   │       ├── 005_unified_sighting_and_proximity.py
│   │       ├── 006_fuzzy_trigram_and_levenshtein.py
│   │       ├── 007_camera_topology.py
│   │       ├── 008_co_occurrence_clusters.py
│   │       └── runner.py                # Automated migration runner
│   ├── messaging/
│   │   └── kafka_client.py              # Apache Kafka producer + MemoryEventBus fallback
│   ├── monitoring/
│   │   ├── camera_state.py              # CameraStateMachine state definitions
│   │   ├── health.py                    # System vitals monitor (CPU, RAM, GPU VRAM, DB, Qdrant)
│   │   └── metrics.py                   # Prometheus text metrics generator
│   ├── recording/
│   │   ├── recorder.py                  # CameraRecorder (30s keyframe-aligned MP4 writer)
│   │   └── retention.py                 # RetentionManager with alert-linked storage immunity
│   ├── routers/
│   │   ├── analytics.py                 # Telemetry, heatmap, traffic speed, AI status endpoints
│   │   ├── cameras.py                   # Camera CRUD, ONVIF discovery, MJPEG streaming
│   │   ├── chat.py                      # Conversational Chatbot & multimodal upload search
│   │   ├── copilot.py                   # Copilot investigation queries & report generation
│   │   ├── elevation.py                 # Privilege elevation request, approval & status endpoints
│   │   ├── playback.py                  # Alerts history, alert ACK, snapshot & video segment serving
│   │   ├── proxy.py                     # SSRF-protected HLS/M3U8 stream proxy
│   │   ├── ptz.py                       # PTZ control router
│   │   ├── records.py                   # Faces, vehicles, plates, captions, OCR ledgers
│   │   ├── rules.py                     # Custom alert rule endpoints
│   │   ├── search.py                    # Semantic dense vector, license plate, face & image search
│   │   ├── settings.py                  # System settings configuration endpoint
│   │   ├── skills_rules.py              # AI skill registry & declarative event fusion rules
│   │   └── topology.py                  # Camera topology graph, node positions, predictive alerts
│   ├── scripts/
│   │   ├── nvr_emulator.py              # Loops local MP4 files into RTSP feeds via FFmpeg
│   │   ├── reset_vms_telemetry.py       # Resets telemetry counters
│   │   └── seed_rtsp_cams.py            # Seeds camera database from JSON config
│   ├── search/
│   │   ├── qdrant_utils.py              # Qdrant client pool & 4-collection vector spaces
│   │   └── vector_search.py             # Qdrant cosine similarity search & time filters
│   ├── services/
│   │   ├── bwc_ingest.py                # Offline batch Body-Worn Camera ingestion & GPX parsing
│   │   ├── bwc_live_ingest.py           # Live cellular Body-Worn Camera registration
│   │   ├── challan.py                   # E-Challan citation generator with QR code
│   │   ├── co_occurrence.py             # Spatial-temporal co-occurrence & convoy clustering
│   │   ├── event_export.py              # Forensic evidence ZIP packager (SHA-256)
│   │   ├── event_fusion.py              # 15s correlation window multimodal event fusion engine
│   │   ├── fir_report.py                # Court-admissible HTML FIR evidence annexure (Section 65B)
│   │   ├── forensics.py                 # Forensic clip export & chain of custody ledger
│   │   ├── identity.py                  # GlobalIdentityManager cross-camera biometric identity merge
│   │   ├── notification_engine.py       # Outbound Webhook, MQTT & Email notification engine
│   │   ├── nvr_adapter.py               # Third-party NVR integration adapter
│   │   ├── onvif_discovery.py           # ONVIF WS-Discovery UDP broadcast scanner
│   │   ├── onvif_ptz.py                 # ONVIF PTZ SOAP control service
│   │   ├── ptz_controller.py            # PTZ motor controller
│   │   ├── ptz_tracker.py               # Automated target PTZ visual tracking service
│   │   ├── stream_manager.py            # CameraStream & StreamManager 4-tier decoder cascade
│   │   ├── stream_resolver.py           # RTSP and YouTube stream resolver
│   │   ├── traffic_analytics.py         # Traffic speed and flow volume analyzer
│   │   ├── trajectory.py                # Cross-camera GPS suspect trajectory reconstruction
│   │   ├── video_qa.py                  # Video QA synthesis service
│   │   ├── copilot/                     # AI Copilot engine & tool routers
│   │   │   ├── chat_engine.py           # Conversational chat engine & trajectory synthesizer
│   │   │   ├── copilot_agent.py         # 18 controlled tool interfaces
│   │   │   ├── multilingual_matcher.py  # Hindi / Gujarati / Hinglish template intent matcher
│   │   │   └── report_generator.py      # Investigation report builder
│   │   ├── detectors/                   # Specialized feature detectors
│   │   │   └── abandoned_object.py      # Abandoned & unattended luggage detector
│   │   ├── integrations/                # External law enforcement integrations
│   │   │   └── cctns_service.py         # CCTNS State Police database integration mock
│   │   ├── topology/                    # Spatial graph routing
│   │   │   └── escape_router.py         # Predictive next-hop escape routing engine
│   │   └── watchlist/                   # POI & Stolen vehicle hot-list matching
│   │       ├── core_router.py           # POI CRUD & DPDP purge router
│   │       ├── matcher.py               # Live ANPR and facial watchlist matching engine
│   │       └── router.py                # Stolen vehicle hot-list endpoints
│   ├── storage/
│   │   └── minio_client.py              # MinIO S3 object storage client (local FS fallback)
│   ├── utils/
│   │   ├── audit.py                     # log_audit_event() forensic audit helper
│   │   ├── security.py                  # safe_join_path() path traversal defense
│   │   ├── ssrf.py                      # Anti-TOCTOU SSRF & DNS rebinding validator
│   │   └── timezone.py                  # IST (+05:30) datetime helper utilities
│   └── workers/
│       └── ai_worker.py                 # CameraAIWorker inference worker thread
├── frontend/
│   ├── index.html                       # Web entry point
│   ├── nginx.conf                       # Production Nginx reverse proxy configuration
│   ├── package.json                     # Node.js dependencies (React 19, MUI v6, Lucide, Recharts)
│   ├── vite.config.js                   # Vite build configuration & API proxy
│   └── src/
│       ├── App.jsx                      # Root application shell, navigation, threat HUD, theme provider
│       ├── index.css                    # Design tokens & glassmorphism styling
│       ├── main.jsx                     # React root mount
│       └── components/
│           ├── AIChatbot.jsx            # Floating conversational AI Copilot chatbot
│           ├── AIChatbot.css            # Chatbot styling & timeline cards
│           ├── AdminConsole.jsx         # User management, RBAC, privilege elevation review, audit logs
│           ├── AlertsPanel.jsx          # Live alert notifications, audio chime, operator ACK
│           ├── ArchivePlayback.jsx      # Historical video playback & timeline scrub
│           ├── CameraManagement.jsx     # Add/edit/delete camera streams & resolution settings
│           ├── DiscoveryScanner.jsx     # ONVIF WS-Discovery network scanner
│           ├── ForensicsManager.jsx     # Forensic ZIP export, FIR reports, E-Challan citations
│           ├── InvestigationSearch.jsx  # Multimodal semantic, plate, face & image search
│           ├── LiveGrid.jsx             # Live multi-camera grid, PTZ controls, canvas overlays
│           ├── LoginModal.jsx           # JWT authentication modal & password reset
│           ├── RecordsConsole.jsx       # Captured ledgers (Faces, Vehicles, Plates, Captions, OCR)
│           ├── SettingsConsole.jsx      # Model toggles, privacy redaction, theme personalization
│           ├── TopologyEditor.jsx       # Interactive 2D camera topological graph editor
│           ├── TopologyEditor.css       # Topology canvas styling
│           ├── TrajectoryMap.jsx        # Cross-camera GPS suspect trajectory & convoy clustering
│           └── WatchlistManager.jsx     # POI and stolen vehicle watchlist manager (DPDP compliance)
├── docs/                                # Modular technical documentation suite
│   ├── ARCHITECTURE.md                  # System architecture, topology, concurrency, pipelines
│   ├── API_REFERENCE.md                 # Complete REST & WebSocket API specification (18+ routers)
│   ├── DATABASE_SCHEMA.md               # 36 SQLAlchemy models, indexes, ER diagram, migrations
│   ├── AI_MODELS_AND_PIPELINES.md       # Computer vision, multimodal VLMs, audio DSP, spatial analytics
│   ├── COPILOT_AND_CHATBOT.md           # Conversational AI, multilingual intent parsing, citations
│   ├── TOPOLOGY_AND_ROUTING.md          # Directed camera graph, predictive escape routing
│   ├── SECURITY_AND_COMPLIANCE.md       # JWT, dynamic TTL elevation, RBAC, SSRF, DPDP, court evidence
│   ├── FORENSICS_AND_WATCHLIST.md       # Evidence bundles, FIR reports, CCTNS, convoy clustering
│   ├── CONFIGURATION_AND_DEPLOYMENT.md  # Environment variables, JSON configs, Docker, deployment
│   ├── TESTING_AND_VALIDATION.md        # 59 test suites, failure injection, validation hierarchy
│   ├── FEATURE_INVENTORY.md             # Master feature catalog & traceability matrix (47 features)
│   └── KNOWN_LIMITATIONS_AND_ROADMAP.md # Technical trade-offs & enterprise scaling roadmap
├── configs/                             # System JSON configurations
│   ├── alerts.json                      # Per-camera alert thresholds
│   ├── cameras.json                     # Camera stream definitions (seeded on init)
│   ├── models.json                      # AI model paths, thresholds, and VLM toggles
│   ├── privacy.json                     # Privacy redaction settings
│   └── zones.json                       # Normalized ROI polygon definitions
├── models/                              # Local ONNX model weights
│   ├── face_detection_yunet_2023mar.onnx
│   └── face_recognition_sface_2021dec.onnx
├── storage/                             # Media storage directory
│   ├── exports/                         # Generated forensic evidence ZIP packages
│   ├── h264_cache/                      # H.264 web transcode cache
│   ├── recordings/                      # 30-second continuous MP4 segments
│   └── snapshots/                       # JPEG alert and track snapshots
├── tests/                               # Root test suite (36 test files)
├── backend/tests/                       # Backend test suite (23 test files)
├── Dockerfile.backend                   # Multi-stage Python 3.10 OpenCV/FFmpeg Docker image
├── Dockerfile.frontend                  # Multi-stage Node 20 / Nginx Docker image
├── docker-compose.yml                   # Infrastructure compose (Postgres, Qdrant, MediaMTX, MinIO, Kafka)
├── manage.ps1                           # Windows PowerShell management script (start/stop/restart)
├── reset_vms_data.py                    # Database and vector storage purge utility
├── requirements.txt                     # Python dependencies
└── PROJECT_DOCUMENTATION.md             # Master single-source-of-truth document
```

---

## 3. Technology Stack

### Backend Stack
| Layer | Technology | Version / Spec | Source File |
|---|---|---|---|
| Web Framework | FastAPI (ASGI async) | Latest | `backend/main.py:202` |
| ASGI Server | Uvicorn | Multi-worker capable | `manage.ps1` |
| Relational Database | PostgreSQL / SQLAlchemy | 15 / ORM Declarative Base | `backend/database/connection.py` |
| Migration Engine | Custom Versioned Runner | 8 sequential migrations | `backend/database/migrations/runner.py` |
| Vector Database | Qdrant | 4 collections (Cosine) | `backend/search/qdrant_utils.py` |
| Event Messaging | Apache Kafka / MemoryEventBus | 4 topics (`alerts`, `captions`, `tracks`, `vehicles`) | `backend/messaging/kafka_client.py` |
| Object Storage | MinIO S3 (boto3) / Local FS | S3 API compliant | `backend/storage/minio_client.py` |
| Object Detection | Ultralytics YOLO | YOLOv8 / YOLO26 (`yolo26l.pt`) | `backend/ai/model_manager.py:96` |
| Multi-Object Tracking | ByteTrack | `bytetrack.yaml` | `backend/ai/model_manager.py:21` |
| Facial Biometrics | YuNet + SFace ONNX | 128d L2-normalized vectors | `backend/ai/face/face_pipeline.py` |
| Vehicle Re-ID | MobileNetV3-Small (torchvision)| 576d Identity feature head | `backend/ai/vehicle/vehicle_reid.py:24` |
| License Plate OCR | PaddleOCR / EasyOCR | v3.x orientation-invariant | `backend/ai/model_manager.py:128` |
| Person Re-ID | MobileNetV3 | 768d feature vector | `backend/ai/person/person_reid.py` |
| Dense Text Embedder | SentenceTransformer | `BAAI/bge-large-en-v1.5` (1024d) | `backend/ai/embeddings/embedder.py:12` |
| Local Scene Captioner | Florence-2 (HuggingFace) | `microsoft/Florence-2-base` | `backend/ai/captioning/captioner.py` |
| Cloud Scene Captioner | Moondream 3.1 REST API | `moondream3.1-9B-A2B` | `backend/ai/captioning/moondream_captioner.py` |
| Acoustic DSP Engine | NumPy FFT + Digital RMS | 16kHz mono 16-bit PCM | `backend/ai/audio/acoustic_engine.py` |
| Video Transcoder | FFmpeg (subprocess) | H.264 AAC keyframe-aligned | `backend/services/forensics.py` |
| Rate Limiter | In-Memory Sliding Window | 10 fails / 5m lockout | `backend/auth/router.py:25` |
| Password Security | bcrypt | Work factor 12 | `backend/auth/helpers.py:56` |
| Authentication | python-jose JWT | HS256 algorithm | `backend/auth/helpers.py:35` |

### Frontend Stack
| Layer | Technology | Source File |
|---|---|---|
| UI Framework | React 19 + React DOM | `frontend/package.json` |
| Build Tool | Vite + `@vitejs/plugin-react` | `frontend/vite.config.js` |
| Component System | Material-UI (MUI v6) | `frontend/src/App.jsx` |
| Icons | Lucide React + MUI Icons | `frontend/src/App.jsx` |
| Telemetry Charts | Recharts | `frontend/src/components/AnalyticsPanel.jsx` |
| Streaming Player | HLS.js + WebRTC WHEP + Canvas | `frontend/src/components/LiveGrid.jsx` |
| Web Server | Nginx Alpine (Reverse Proxy) | `frontend/nginx.conf` |

---

## 4. System Architecture & Master Topology

### 4.1 Master System Topology & Component Interconnect
Refer to the detailed architectural topology and subsystem diagrams in [docs/ARCHITECTURE.md](file:///d:/sybau_granth/docs/ARCHITECTURE.md).

### 4.2 Concurrency Model & Multithreading Architecture
- **Per-Camera Ingestion Threads (`CameraStream._capture_loop`)**: Runs in an isolated thread per stream. Decodes frames via the 4-tier hardware cascade and updates atomic buffer `CameraStream.latest_frame` under a `threading.Lock()`.
- **Per-Camera Recorder Threads (`CameraRecorder`)**: Continuously segments 30-second raw MP4 video slices to disk with H.264 transcoding.
- **Per-Camera AI Worker Threads (`CameraAIWorker`)**: Periodically samples frames every $N$ frames and submits inference requests to `InferenceScheduler`.
- **Inference Scheduler (`InferenceScheduler`)**: Collects incoming frames into a dynamic micro-batch queue (flushed every 15ms or when batch reaches 8). Serializes CUDA forward passes under `model_manager.gpu_lock` to eliminate VRAM deadlocks.
- **Secondary Consumer Queue (`secondary_consumers.py`)**: Asynchronous background queue for heavy Florence-2 captions and dense vector embeddings with dynamic load shedding when queue length $\ge 100$.

### 4.3 Multi-Tenancy & Tenant Data Segregation
All database models incorporate indexed `organization_id` (e.g. `"org_default"`) and `site_id` (e.g. `"site_main"`) columns. All query filters and live alerts enforce tenant isolation across police departments and smart city administrative boundaries.

---

## 5. Data Flow & Pipeline Stages

1. **Ingestion & Decode Cascade**: `GStreamer NVDEC` $\rightarrow$ `FFmpeg CUDA` $\rightarrow$ `Native OpenCV CPU` $\rightarrow$ `Sub-stream Failover (101 -> 102)`.
2. **Micro-Batch Inference**: Frames accumulated into 15ms micro-batches and processed via batched CUDA tensors.
3. **Dual-Path Router**: Zero-latency WebSocket push to React canvas (Path A) vs Async secondary deep model queue (Path B).
4. **Multi-Space Vector Indexing**: Vectors indexed into 4 isolated Qdrant spaces (`face`, `vehicle`, `person_crop`, `scene`).
5. **Conversational Copilot**: Intent parsing across English, Hindi, and Gujarati, multi-camera trajectory synthesis, and visual citations.
6. **Predictive Escape Routing**: Kinematic graph traversal calculating downstream arrival time windows and interception probabilities.
7. **Dynamic Privilege Elevation**: Ephemeral role promotion in `get_current_user` with TTL expiration and strict self-approval blocking.
8. **Multimodal Event Fusion**: 15-second correlation window generating compound high-risk events (e.g. Intrusive Person + Acoustic Glass Break $\rightarrow$ Critical Break-In).
9. **Forensics & Custody**: SHA-256 signed ZIP packages, court FIR annexures (Section 65B), and E-Challans.
10. **Watchlist & DPDP Purge**: Live CCTNS cross-referencing and automated 90-day retention purging.

---

## 6. AI / ML Models & Perception Engines

Refer to [docs/AI_MODELS_AND_PIPELINES.md](file:///d:/sybau_granth/docs/AI_MODELS_AND_PIPELINES.md) for full architectural parameters, layer specifications, and mathematical formulations.

Key Models:
- **YOLOv8 / YOLO26**: Object detection and spatial localization (`yolo26l.pt`, confidence $\ge 0.35$).
- **ByteTrack**: Multi-object tracking with EMA velocity and 30-centroid path history.
- **YuNet + SFace ONNX**: 128d facial biometrics (cosine threshold $\ge 0.40$).
- **MobileNetV3**: Vehicle Re-ID (576d), Person Re-ID (768d), and HSV clothing color classification.
- **PaddleOCR / EasyOCR**: Alphanumeric license plate text extraction with Indian state normalization.
- **Florence-2 Local VLM**: Dense `<MORE_DETAILED_CAPTION>` scene descriptions with SHA-256 image binding.
- **Moondream 3.1 Cloud VLM API**: Interleaved half-phase cloud captioning with API key round-robin pool.
- **SentenceTransformer `BAAI/bge-large-en-v1.5`**: 1024d text vector embeddings for semantic search.
- **Acoustic Intelligence Engine**: 16kHz PCM FFT/RMS spectral analysis (gunshots, screams, glass breaks, explosions).
- **Spatial Analytics Suite**: Directional line crossing (2D cross product), tailgating, fall detection ($v_y > 120\text{px/s}$), PPE safety compliance, queue dwell time, and parking overstay.
- **Adaptive Baseline Engine**: Per-camera hourly occupant z-scores ($Z \ge 3.0 \rightarrow \text{ANOMALOUS\_ACTIVITY}$).
- **Indian Traffic Geometry Normalizer**: Aspect ratio filter ($0.75 \le w/h \le 1.45$) converting truck/car errors to auto-rickshaws.

---

## 7. API Reference (All 18+ Routers)

Refer to [docs/API_REFERENCE.md](file:///d:/sybau_granth/docs/API_REFERENCE.md) for complete endpoint specifications, query parameters, request bodies, and responses.

Summary of Mounted Sub-Routers:
1. `backend/auth/router.py`: `/api/v1/auth` (Login, Register, Password Change)
2. `backend/routers/elevation.py`: `/api/v1/elevation` (Privilege Elevation Requests, Approvals, Status)
3. `backend/routers/cameras.py`: `/api/v1/cameras` & `/api` alias (Cameras, ONVIF Scan, Zones, Streams)
4. `backend/routers/topology.py`: `/api/v1/topology` (Graph Nodes, Edges, Layout Reset, Predictive Alerts)
5. `backend/routers/copilot.py`: `/api/v1/copilot` (Investigation Queries, Reports, Tool Interfaces)
6. `backend/routers/chat.py`: `/api/v1/chat` (Multi-Turn Chat, Multimodal Upload Search, History)
7. `backend/routers/search.py`: `/api/v1/search` (Semantic, Plate, Face, Multimodal Image Search)
8. `backend/routers/playback.py`: `/api/v1/alerts`, `/api/v1/playback` (Alerts, ACK, Snapshots, Recordings)
9. `backend/routers/records.py`: `/api/v1/records`, `/api/v1/florence` (Faces, Vehicles, Plates, Captions, OCR Ledgers)
10. `backend/services/forensics.py`: `/api/v1/forensics` (Evidence ZIP Export, Chain of Custody)
11. `backend/services/fir_report.py`: `/api/v1/forensics/fir-report` (Section 65B HTML FIR Annexures)
12. `backend/services/trajectory.py`: `/api/v1/forensics/trajectory` (Cross-Camera GPS Route Reconstruction)
13. `backend/services/co_occurrence.py`: `/api/v1/forensics/co-occurrence` (Convoy Clustering & Review)
14. `backend/routers/skills_rules.py`: `/api/v1/skills`, `/api/v1/event-rules` (AI Skill Registry & Event Rules)
15. `backend/services/watchlist/`: `/api/v1/watchlist` (POIs, Stolen Vehicle Hot-List, DPDP Purge)
16. `backend/routers/analytics.py`: `/api/v1/analytics`, `/api/v1/ai`, `/api/v1/monitor` (Telemetry, Heatmaps)
17. `backend/admin/router.py`: `/api/v1/admin` (User Administration, Soft/Hard Delete, Audit Logs)
18. `backend/services/challan.py`: `/api/v1/challan` (E-Challan Citation with QR Code)
19. `backend/main.py`: `/healthz`, `/readyz`, `/metrics`, `/api/v1/bwc/live/register`, `/api/v1/ws/alerts`

---

## 8. Database Schema (All 36 Models)

Refer to [docs/DATABASE_SCHEMA.md](file:///d:/sybau_granth/docs/DATABASE_SCHEMA.md) for complete column definitions, foreign keys, compound indexes, and migration scripts.

Catalog of 36 Models:
1. `User` (`users`)
2. `PrivilegeElevationRequest` (`privilege_elevation_requests`)
3. `Camera` (`cameras`)
4. `CameraNode` (`camera_nodes`)
5. `CameraEdge` (`camera_edges`)
6. `CameraTopology` (`camera_topologies`)
7. `CameraHealthLog` (`camera_health_logs`)
8. `CameraBaseline` (`camera_baselines`)
9. `CanonicalEvent` (`events`, alias `Alert`)
10. `Track` (`tracks`)
11. `Face` (`faces`)
12. `Vehicle` (`vehicles`)
13. `RawOCR` (`raw_ocr_records`)
14. `SceneCaption` (`scene_captions`)
15. `UnifiedSighting` (`unified_sightings`)
16. `GlobalIdentity` (`global_identities`)
17. `PersonJourneyEvent` (`person_journey_events`)
18. `VehicleJourneyEvent` (`vehicle_journey_events`)
19. `CoOccurrenceCluster` (`co_occurrence_clusters`)
20. `AudioEvent` (`audio_events`)
21. `EvidenceLedger` (`evidence_ledger`)
22. `EvidenceChainOfCustody` (`evidence_chain_of_custody`)
23. `AuditLog` (`audit_logs`)
24. `QueryAuditLog` (`query_audit_logs`)
25. `SearchHistory` (`search_history`)
26. `AISkillRegistry` (`ai_skills_registry`)
27. `CameraSkillAssignment` (`camera_skill_assignments`)
28. `EventRule` (`event_rules`)
29. `CustomAlertRule` (`custom_alert_rules`)
30. `AlertConfig` (`alert_configs`)
31. `Zone` (`zones`)
32. `ChatSession` (`chat_sessions`)
33. `ChatMessage` (`chat_messages`)
34. `Investigation` (`investigations`)
35. `StolenVehicleWatchlist` (`stolen_vehicles_watchlist`)
36. `PersonWatchlist` (`person_watchlist`)

---

## 9. Configuration Files & System Settings

Refer to [docs/CONFIGURATION_AND_DEPLOYMENT.md](file:///d:/sybau_granth/docs/CONFIGURATION_AND_DEPLOYMENT.md) for full JSON configurations and environment settings (`configs/models.json`, `configs/alerts.json`, `configs/privacy.json`, `configs/zones.json`, `configs/cameras.json`).

---

## 10. Environment Variables Catalog

Refer to [docs/CONFIGURATION_AND_DEPLOYMENT.md](file:///d:/sybau_granth/docs/CONFIGURATION_AND_DEPLOYMENT.md) for complete `.env` catalog (`DATABASE_URL`, `VMS_SECRET_KEY`, `APP_ENV`, `CORS_ALLOWED_ORIGINS`, `KAFKA_BOOTSTRAP_SERVERS`, `QDRANT_HOST`, `MINIO_ENDPOINT`, `MOONDREAM_API_KEYS`, etc.).

---

## 11. Master Feature Inventory (47 Features)

Refer to [docs/FEATURE_INVENTORY.md](file:///d:/sybau_granth/docs/FEATURE_INVENTORY.md) for the complete 47-feature validation and traceability matrix.

---

## 12. Infrastructure & Container Deployment

- Multi-stage Docker backend (`Dockerfile.backend`) on `python:3.10-slim` with OpenCV & FFmpeg.
- Multi-stage Docker frontend (`Dockerfile.frontend`) with Node 20 and Nginx reverse proxy.
- Compose services: PostgreSQL 15, Qdrant Vector DB, MediaMTX RTSP/HLS/WHEP gateway, MinIO S3 object storage, and Apache Kafka cluster.

---

## 13. Setup & Running Locally

### Windows (PowerShell)
```powershell
.\manage.ps1 start    # Launches Docker containers, runs migrations, starts backend & frontend
.\manage.ps1 stop     # Halts all running services
.\manage.ps1 restart  # Restarts system cleanly
```

### Automated Testing
```powershell
.venv\Scripts\python.exe -m pytest
```

### Access Endpoints
- Web Frontend: `http://localhost:5173`
- Backend API / Docs: `http://localhost:8000/docs`
- Qdrant Vector Dashboard: `http://localhost:6333/dashboard`
- MinIO Storage Console: `http://localhost:9001`
- MediaMTX HLS Stream: `http://localhost:8888/{camera_id}/index.m3u8`

---

## 14. Security Architecture & DPDP Compliance

Refer to [docs/SECURITY_AND_COMPLIANCE.md](file:///d:/sybau_granth/docs/SECURITY_AND_COMPLIANCE.md) for full security controls:
- **JWT & Password Complexity**: HS256 signing with 8-hour lifetime and bcrypt work factor 12.
- **Dynamic Privilege Elevation (FEAT-02)**: Ephemeral TTL role promotion in `get_current_user` with strict self-approval prevention.
- **Anti-TOCTOU SSRF Defense (SEC-05)**: Multi-record DNS rebinding resolution and private IP range blocking.
- **Path Traversal Defense**: Canonical path validation via `safe_join_path()`.
- **DPDP Act 2023 Compliance**: 3-tier POI retention tracking and automated 90-day data purging.
- **Court Admissibility (Section 65B)**: SHA-256 signed evidence ZIP packages and verified HTML FIR annexures.
- **Brute-Force Rate Limiting**: 10 failed attempts / 5 min window $\rightarrow$ 15 min lockout.

---

## 15. Known Limitations & Engineering Roadmap

Refer to [docs/KNOWN_LIMITATIONS_AND_ROADMAP.md](file:///d:/sybau_granth/docs/KNOWN_LIMITATIONS_AND_ROADMAP.md) for detailed engineering boundaries:
1. **Single-Node GPU Serialization (`gpu_lock`)**: Mitigated by 15ms dynamic micro-batching. Roadmap: NVIDIA DeepStream & Triton Inference Server across GPU clusters.
2. **Speed Metrics in Pixels/Sec**: Converted to relative velocity. Roadmap: Interactive 4-point homography quad calibration.
3. **Dual Hash Evidence Model**: Stores both `exported_clip_sha256` and `source_segments_sha256` for unbroken chain-of-custody proof in court.
4. **SSRF Proxy Defense**: Enforces multi-address DNS verification.

---

## 16. Dependency Index

Refer to [requirements.txt](file:///d:/sybau_granth/requirements.txt) and [frontend/package.json](file:///d:/sybau_granth/frontend/package.json) for exact Python and Node.js package manifests.

---

## 17. Unique Selling Points (USPs) & Architectural Differentiators

| Industry Problem in Generic VMS | Sybau VMS Pro Solution & Technical Innovation | Source Module |
|---|---|---|
| **VRAM Contention & GPU Deadlocks** | Dynamic 15ms micro-batch priority scheduler (`InferenceScheduler`) under unified `gpu_lock`. | `backend/ai/scheduler.py` |
| **Heavy VLM Queue Latency** | Zero-latency Dual-Path Router (Path A for live UI canvas vs Path B for async models with load shedding). | `backend/ai/routing/downstream_router.py` |
| **Indian 3-Wheeler Misclassifications** | Geometry-Aware Traffic Normalizer converting truck/car errors to auto-rickshaws. | `backend/ai/pipeline/orchestrator.py` |
| **Stream Disconnects & Network Drops** | 4-tier hardware decoder cascade with sub-stream auto-failover (`101` $\rightarrow$ `102`) and exponential backoff (2s $\rightarrow$ 60s). | `backend/services/stream_manager.py` |
| **Court Evidence Inadmissibility** | Cryptographically signed SHA-256 ZIP packages, chain-of-custody logs, and Section 65B HTML FIR reports. | `backend/services/event_export.py`, `backend/services/fir_report.py` |
| **Single Vector Space Collisions** | 4 isolated Qdrant vector spaces (`face`, `vehicle`, `person_crop`, `scene`). | `backend/search/qdrant_utils.py` |
| **DPDP Data Retention Violations** | 3-tier retention status tracking and automated 90-day hard-delete purging with audit logs. | `backend/services/watchlist/core_router.py` |
| **Manual Escaped Suspect Tracking** | Draggable camera topology graph with predictive next-hop escape routing and velocity ETAs. | `backend/services/topology/escape_router.py` |
| **Conversational Copilot in Indian Context** | Native Hindi, Gujarati, and Hinglish intent parsing, multi-camera trajectory synthesis, and citations. | `backend/services/copilot/chat_engine.py`, `backend/services/copilot/multilingual_matcher.py` |
| **Static RBAC Inflexibility** | Dynamic TTL privilege elevation workflow with self-approval prevention and automatic expiration. | `backend/routers/elevation.py`, `backend/auth/helpers.py` |
| **Audio Anomaly Blindness** | 16kHz PCM FFT/RMS acoustic intelligence engine with 3-window temporal smoothing confirmation. | `backend/ai/audio/acoustic_engine.py` |
| **Isolated Sightings & Accomplice Blindness**| Cross-camera spatio-temporal convoy clustering with investigator review workflow. | `backend/services/co_occurrence.py` |
| **Accidental Deletion of Critical Evidence** | Retention manager enforces disk limits while providing deletion immunity to alert-linked recordings. | `backend/recording/retention.py` |

---

*Master project documentation verified line-by-line against the complete active codebase — August 2026.*
