# SYBAU AI Surveillance & Forensic VMS — Complete Implementation Audit & Production Architecture

**Date:** August 12, 2026  
**Auditor:** Principal VMS Architect & Senior Engineering Team  
**Repository:** SYBAU (`c:\projects\sybau`)  

---

## 1. Executive Summary

This audit assesses the readiness of the SYBAU codebase for upgrade into a production-grade, deployable AI Forensic Video Intelligence Platform. The repository contains foundational streaming, object detection, database models, and web UI components. However, significant architectural gaps, mock/template logic, missing real-time audio analytics, incomplete forensic investigation tools, and unhardened deployment configurations exist.

Following a deep architecture review, the implementation strategy incorporates critical production VMS principles:
1. **Media Layer Decoupling & Recording Invariant**: FFmpeg/PyAV/MediaMTX as the primary media transport; OpenCV reserved for downstream frame consumption. **Recording is completely isolated and MUST continue when AI, VLM, Qdrant, or notification services fail.**
2. **Configurable Queue Sizes & Policies**: Configurable queue bounds per type (`frame`, `inference`, `recording`, `forensic`, `notification`) with explicit overflow strategies (`drop_oldest`, `NEVER_DROP`, `PERSIST`, `PERSIST_COALESCE`).
3. **Canonical Event Schema, Lineage & State Ownership**: Uniform event contract with `deduplication_key` idempotency, parent/source event lineage (`parent_event_id`, `source_event_ids[]`), and strict state ownership (Detector → `DETECTED`; Fusion → `CONFIRMED`; Rule → `ACTIVE`; Resolution → `RESOLVED`; Retention → `ARCHIVED`).
4. **Normalized Journey Tables & Concrete Re-ID Models**: Normalized `PersonJourneyEvent` and `VehicleJourneyEvent` tables (with JSON as derived cache only). Explicit Re-ID models specified: OSNet (`osnet_x1_0` 512D) for Person Re-ID, FastReID (`res50` 2048D) for Vehicle Re-ID, constrained by a physical `CameraTopology` graph.
5. **AI Skill Registry First**: Standardized `AISkill` interface built prior to new perception modules.
6. **Cached Privacy Derivatives**: Pre-calculated privacy-rendered video derivatives stored in object storage instead of expensive per-request transcoding.
7. **Strict SSRF TOCTOU & Redirect Protection**: DNS resolution and IP validation before socket connection, re-validating every redirect against blocked CIDRs (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.169.254`).
8. **Time-Partitioned PostgreSQL Tables**: Declarative range partitioning by time on high-volume tables (`events`, `detections`, `tracks`, `camera_health_logs`, `audit_logs`, `journey_events`).
9. **Production Vertical Slices & Hard Sign-Off**: Iterative delivery via 5 vertical slices. Feature status tracked in `docs/FEATURE_STATUS.md` requiring all pass checks before marking Production.

---

## 2. Comprehensive Component Audit

### 2.1 Media Plane & Streaming (`backend/services/stream_manager.py`, `backend/recording/`)
- **Status:** Partially Functional
- **Existing Strengths:** Basic stream reading and sub-stream failover.
- **Identified Gaps:**
  - OpenCV `VideoCapture` used as central transport rather than MediaMTX / PyAV / FFmpeg demuxer.
  - Recording is tied to the frame reading loop; AI pipeline bottlenecks can degrade stream persistence.
  - No audio stream demuxing or PCM chunking pipeline.

### 2.2 AI Plane & Perception Pipeline (`backend/ai/`)
- **Status:** Partially Functional
- **Existing Strengths:** YOLO detection, EasyOCR, SFace 128D embeddings, Florence-2 captioner.
- **Identified Gaps & Weaknesses:**
  - `acoustic_engine.py`: Simple dB/FFT heuristics. Needs clear separation of **Audio Anomaly Detection** (energy/spectral shift) vs **Audio Semantic Classification** (ML classifier model) with model versioning and temporal window smoothing.
  - Pose estimation, PPE, Queue, Parking, Tailgating, and Baselines missing.
  - Frame Governor: Operates at static 2-3 FPS without GPU queue backpressure control.
  - Re-ID: Lacks camera spatial topology and temporal constraints, causing high false-match rates across distant cameras. Needs concrete OSNet / FastReID implementation.

### 2.3 Event & Fusion Plane (`backend/workers/ai_worker.py`, `backend/messaging/`)
- **Status:** Incomplete
- **Identified Gaps:**
  - Lacks a canonical `Event` schema contract with idempotency/deduplication key logic and parent event lineage (`source_event_ids`).
  - No strict state-transition ownership (`DETECTED` → `CONFIRMED` → `ACTIVE` → `RESOLVED` → `ARCHIVED`).
  - Visual and audio events are handled independently without a compound risk fusion matrix.

### 2.4 Data & Storage Plane (`backend/database/`, `backend/search/`, `backend/storage/`)
- **Status:** Functional Foundation, Needs Production Scaling
- **Identified Gaps:**
  - Missing PostgreSQL time-partitioning and indexing on high-volume tables (`events`, `detections`, `tracks`, `camera_health`, `journey_events`).
  - Journey trajectory stored as JSON strings rather than normalized SQL relations.
  - Missing Multi-tenancy scoping fields (`organization_id`, `site_id`).
  - Video privacy rendering lacks cached derivative management in object storage (MinIO).

### 2.5 Forensic Plane & AI Copilot (`backend/services/forensics.py`, `backend/services/video_qa.py`)
- **Status:** Incomplete / Template Code
- **Identified Gaps:**
  - `video_qa.py` is a text format template. Copilot requires strict tool routing, input/output validation, permissions, timeouts, rate limits, timeline synthesis, and evidence citations.
  - Evidence integrity (SHA-256) conflated with Chain of Custody (provenance + access/handling history + signature).

### 2.6 Security & Hardening (`backend/auth/`, `backend/main.py`)
- **Status:** Moderate Security Risk
- **Identified Gaps:**
  - Simple URL string checks for SSRF. Must implement comprehensive SSRF protection preventing TOCTOU DNS rebinding and re-validating redirects covering private IPv4/IPv6, loopback, link-local, cloud metadata, and external URLs.

---

## 3. Revised Target Production Architecture

```text
                               CAMERAS (RTSP / ONVIF / File)
                                            │
                                            ▼
                                  MEDIAMTX / FFMPEG / PYAV
                                 (Central Transport Plane)
                                            │
                  ┌─────────────────────────┼─────────────────────────┐
                  ▼                         ▼                         ▼
            RECORDING ENGINE            LIVE STREAM            AUDIO & FRAME EXTR.
         (INVARIANT: Continuous)     (WebRTC / HLS Proxy)       (Bounded Config Queues)
                  │                                                   │
                  ▼                                                   ▼
            OBJECT STORAGE                                    ADAPTIVE FRAME GOVERNOR
            (MinIO / Disk)                                (Driven by GPU Queue Depth)
                                                                      │
                                          ┌───────────────────────────┴───────────────────────────┐
                                          ▼                                                       ▼
                                   VIDEO AI PLANE                                          AUDIO AI PLANE
                          (YOLO, Face, Pose, OSNet, VLM)                                (FFT Anomaly + ML Classifier)
                                          │                                                       │
                                          └───────────────────────────┬───────────────────────────┘
                                                                      ▼
                                                       MULTIMODAL EVENT FUSION ENGINE
                                                      (Canonical Schema + Lineage + Idempotency)
                                                                      │
                                                                      ▼
                                                       METADATA, VECTOR & EVIDENCE STORE
                                                   (Partitioned Postgres + Qdrant + MinIO)
                                                                      │
                                                                      ▼
                                                       FORENSIC & INVESTIGATION PLANE
                                             ├─ Topology-Constrained OSNet / FastReID Journey
                                             ├─ Adaptive Camera Health & Behavioral Baselines
                                             ├─ Cached Privacy Derivative Generator (6 Modes)
                                             ├─ Multi-Modal Forensic Timeline
                                             ├─ AI Copilot (18 Controlled Tool Interfaces)
                                             └─ SHA-256 Signed Evidence Manifest & Custody Ledger
                                                                      │
                                                                      ▼
                                                        PRESENTATION PLANE (React VMS)
```

---

## 4. Architectural Directives & Final Gate Invariants

1. **Hard Recording Invariant**: Video recording runs in a dedicated isolated worker thread/process. **Recording MUST continue when AI, VLM, Qdrant, or notification services fail.**
2. **Canonical Event Schema & Lineage**: Events adhere to a single unified `Event` model containing `deduplication_key`, `parent_event_id`, `source_event_ids[]`, state (`DETECTED`, `CONFIRMED`, `ACTIVE`, `RESOLVED`, `ARCHIVED`), `confidence`, `severity`, `model_name`, `model_version`, `inference_backend`, and `metadata`. State transitions are strictly owned by domain components (Detector → `DETECTED`, Fusion → `CONFIRMED`, Rule → `ACTIVE`, Resolution → `RESOLVED`, Retention → `ARCHIVED`). Arbitrary status patches from the frontend are rejected.
3. **Configurable Queues & Backpressure**: Queue bounds are configured per type (`frame`: 100/drop_oldest, `inference`: 50/drop_oldest, `recording`: 500/never_drop, `forensic`: 1000/persist, `notification`: 200/coalesce).
4. **Normalized Journey Events**: `PersonJourneyEvent` and `VehicleJourneyEvent` are normalized database entities. JSON trajectory strings are used only for derived/cached representation.
5. **Concrete Re-ID Models**: Person Re-ID uses OSNet (`osnet_x1_0` 512D embeddings). Vehicle Re-ID uses FastReID (`res50` 2048D embeddings). All cross-camera matching is constrained by a physical `CameraTopology` transition graph.
6. **Cached Privacy Derivatives**: Full-video privacy redaction pre-generates and caches redacted video files in object storage instead of per-request live transcoding.
7. **Controlled Copilot Tool Execution**: Copilot executes strictly via authorized Python service wrappers (`User → LLM → Tool Router → Auth/Schema Validation → Service → DB → Evidence → LLM`). Direct SQL/shell execution is forbidden.
8. **Strict Anti-SSRF Socket & Redirect Validation**: Network sockets resolve DNS once and check resolved IPs against blocked ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.169.254`), re-validating every HTTP redirect before following.
9. **Time-Partitioned PostgreSQL**: High-volume tables (`events`, `detections`, `tracks`, `camera_health_logs`, `audit_logs`, `journey_events`) use time-based partitioning.
10. **Strict Sign-Off Matrix**: No feature is marked `Production` until its `docs/FEATURE_STATUS.md` matrix has `PASS` across Backend, AI, DB, API, Frontend, Tests, and E2E.

---

*This architecture specification is complete and approved for immediate execution.*
