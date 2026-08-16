# API Reference — Sybau VMS Pro

> **Comprehensive REST and WebSocket API specification for Sybau VMS Pro.**
> All endpoints are mounted under `/api/v1` (with `/api` legacy aliases where noted). Authentication requires standard Bearer JWT tokens unless designated as public.

---

## Table of Contents
1. [Authentication & Session Control (`/api/v1/auth`)](#1-authentication--session-control)
2. [Dynamic Privilege Elevation Workflow (`/api/v1/elevation`)](#2-dynamic-privilege-elevation-workflow)
3. [Camera Management & ONVIF Discovery (`/api/v1/cameras`)](#3-camera-management--onvif-discovery)
4. [Camera Topology & Predictive Routing (`/api/v1/topology`)](#4-camera-topology--predictive-routing)
5. [AI Investigation Copilot (`/api/v1/copilot`)](#5-ai-investigation-copilot)
6. [Conversational AI Chatbot (`/api/v1/chat`)](#6-conversational-ai-chatbot)
7. [Multimodal Forensic Search (`/api/v1/search`)](#7-multimodal-forensic-search)
8. [Surveillance Alerts & Playback (`/api/v1/alerts`, `/api/v1/playback`)](#8-surveillance-alerts--playback)
9. [Captured Records Ledgers (`/api/v1/records`)](#9-captured-records-ledgers)
10. [Forensics, Evidence & Trajectory (`/api/v1/forensics`)](#10-forensics-evidence--trajectory)
11. [AI Skills Registry & Event Rules (`/api/v1/skills`, `/api/v1/event-rules`)](#11-ai-skills-registry--event-rules)
12. [POI & Stolen Vehicle Watchlists (`/api/v1/watchlist`)](#12-poi--stolen-vehicle-watchlists)
13. [Analytics, Telemetry & Heatmaps (`/api/v1/analytics`, `/api/v1/monitor`)](#13-analytics-telemetry--heatmaps)
14. [System Administration (`/api/v1/admin`)](#14-system-administration)
15. [E-Challan & Citations (`/api/v1/challan`)](#15-e-challan--citations)
16. [Infrastructure, Health & Metrics (`/healthz`, `/readyz`, `/metrics`)](#16-infrastructure-health--metrics)
17. [WebSocket Real-Time Alert Stream (`/api/v1/ws/alerts`)](#17-websocket-real-time-alert-stream)

---

## 1. Authentication & Session Control

Mounted at: `backend/auth/router.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Public | OAuth2 password form login. Returns JWT access token, user role, and `must_change_password` flag. Rate-limited to 10 failed attempts / 5 min window (15-min lockout). |
| `POST` | `/api/v1/auth/register` | `admin` | Registers a new user with base role and camera ACL. Automatically flags `must_change_password=True`. |
| `POST` | `/api/v1/auth/change-password` | Authenticated | Updates current user password. Clears `must_change_password` flag upon successful validation. |

---

## 2. Dynamic Privilege Elevation Workflow

Mounted at: `backend/routers/elevation.py` (FEAT-02)

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `POST` | `/api/v1/elevation/request` | `viewer` | Submits a time-limited privilege elevation request (`requested_role`: `admin`/`operator`, `reason`, `ttl_minutes`: 5 to 480). Returns `request_uuid`. |
| `GET` | `/api/v1/elevation/requests` | `viewer` | Lists elevation requests. Admins view all organization requests; non-admins view only their own requests. Optional `?status=PENDING`. |
| `POST` | `/api/v1/elevation/requests/{request_uuid}/approve` | `admin` | Approves request. **Strict rule**: Self-approval is strictly forbidden (HTTP 403). Promotes user effective role for `ttl_minutes`. |
| `POST` | `/api/v1/elevation/requests/{request_uuid}/reject` | `admin` | Rejects elevation request with optional review comments. |
| `POST` | `/api/v1/elevation/requests/{request_uuid}/revoke` | `admin` | Immediately revokes an active approved privilege elevation. |
| `GET` | `/api/v1/elevation/status` | `viewer` | Returns authenticated user's `base_role`, `effective_role`, `is_elevated`, and `seconds_remaining`. |

---

## 3. Camera Management & ONVIF Discovery

Mounted at: `backend/routers/cameras.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/cameras` | `viewer` | Lists all configured cameras with live telemetry, HLS/WebRTC streaming endpoints, and FPS. |
| `POST` | `/api/v1/cameras` | `operator` | Adds a new camera stream. Spawns dedicated `CameraRecorder` and `CameraAIWorker` daemon threads. |
| `PUT` | `/api/v1/cameras/{id}` | `operator` | Updates camera metadata, resolution, or stream URL (restarts ingestion workers if URL changes). |
| `DELETE` | `/api/v1/cameras/{id}` | `operator` | Removes camera and halts background workers. Cascades associated zone rules. |
| `POST` | `/api/v1/cameras/scan` | `viewer` | Runs WS-Discovery UDP broadcast scan on local subnet to detect ONVIF-compliant IP cameras. |
| `POST` | `/api/v1/cameras/resolve-onvif` | `viewer` | Resolves RTSP stream URI from discovered ONVIF camera via SOAP Profile extraction. |
| `GET` | `/api/v1/cameras/{id}/zones` | `viewer` | Retrieves configured ROI polygons for loitering, restricted areas, and line-crossing. |
| `POST` | `/api/v1/cameras/{id}/zones` | `admin` | Replaces/saves normalized `[[x,y],...]` zone polygons for a camera. |
| `GET` | `/api/v1/cameras/{id}/stream` | `viewer` | Resolves optimal streaming URL format (`HLS`, `WebRTC`, `MJPEG`). |
| `GET` | `/api/v1/cameras/{id}/mjpeg` | Public | Provides low-overhead multipart MJPEG video stream (~25fps) for browser preview canvas. |

---

## 4. Camera Topology & Predictive Routing

Mounted at: `backend/routers/topology.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/topology` | `viewer` | Fetches full camera topological graph (all nodes with map coordinates + all active directed edges). |
| `PUT` | `/api/v1/topology/nodes/{camera_id}` | `operator` | Persists user-dragged canvas coordinates (`map_x`, `map_y`, `zone_group`, `geo_lat`, `geo_lng`). |
| `POST` | `/api/v1/topology/edges` | `operator` | Creates or updates directed transit edge between camera nodes with distance, min/max transit seconds, and heading rules. |
| `DELETE` | `/api/v1/topology/edges/{edge_id}` | `operator` | Deletes a directed topological transit edge. |
| `POST` | `/api/v1/topology/reset-layout` | `operator` | Resets node layout to canonical geometry without deleting configured edge transit rules. |
| `POST` | `/api/v1/topology/predict` | `operator` | Evaluates suspect departure from Cam A, calculates velocity bounds, and broadcasts predictive transit alerts for downstream cameras. |

---

## 5. AI Investigation Copilot

Mounted at: `backend/routers/copilot.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `POST` | `/api/v1/copilot/query` | `viewer` | Executes natural language investigation query (`?question=...`) via controlled multi-tool execution. |
| `GET` | `/api/v1/copilot/report/{investigation_id}` | `operator` | Generates a court-admissible forensic evidence report for an investigation session. |
| `GET` | `/api/v1/copilot/tools` | `viewer` | Returns schema definitions for all 18 controlled tool interfaces available to Copilot. |

---

## 6. Conversational AI Chatbot

Mounted at: `backend/routers/chat.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/chat/sessions` | `viewer` | Lists past conversational investigation sessions for the authenticated user. |
| `POST` | `/api/v1/chat/session/new` | `viewer` | Initializes a new persistent chat session (`session_uuid`). |
| `DELETE` | `/api/v1/chat/session/{session_id}` | `viewer` | Deletes a chat session and its conversation history. |
| `POST` | `/api/v1/chat/message` | `viewer` | Processes multi-turn text queries (supports English, Hindi, and Gujarati). Returns synthesized answer, trajectory timeline cards, and citations. |
| `POST` | `/api/v1/chat/upload-search` | `viewer` | Multimodal visual upload + text query. Extracts visual features and returns ranked matching records with timeline context. |
| `GET` | `/api/v1/chat/history` | `viewer` | Fetches paginated message history for a session (`?session_id=...&limit=50&before_id=...`). |
| `GET` | `/api/v1/chat/suggestions` | `viewer` | Returns tactical Hinglish/English surveillance prompt suggestions for investigators. |

---

## 7. Multimodal Forensic Search

Mounted at: `backend/routers/search.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/search/semantic` | `viewer` | Natural language dense vector search over scene captions via SentenceTransformer `BAAI/bge-large-en-v1.5` in Qdrant. |
| `GET` | `/api/v1/search/license-plate` | `viewer` | Alphanumeric license plate search across OCR and vehicle tables with wildcard support. |
| `POST` | `/api/v1/search/face` | `viewer` | Uploads face crop image, extracts 128d SFace embedding, and queries Qdrant `face` vector collection. |
| `POST` | `/api/v1/search/image-query` | `viewer` | Fast multimodal image query (<30ms): extracts face biometrics, YOLO object classes, and OpenCLIP clothing embeddings. |
| `GET` | `/api/v1/search/debug` | `viewer` | Telemetry diagnostic endpoint reporting vector collection sizes, Qdrant health, and snapshot counts. |

---

## 8. Surveillance Alerts & Playback

Mounted at: `backend/routers/playback.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/alerts` | `viewer` | Fetches recent canonical surveillance alerts with severity filtering, pagination, and timestamps. |
| `POST` | `/api/v1/alerts/{id}/acknowledge` | `operator` | Marks alert as acknowledged by the operator in the database. |
| `GET` | `/api/v1/alerts/{id}/export` | `operator` | Triggers keyframe-aligned evidence extraction and downloads SHA-256 signed evidence ZIP bundle. |
| `GET` | `/api/v1/playback/snapshot/{snap_id}` | `viewer` | Serves JPEG snapshot image (with fallback placeholder if missing). |
| `GET` | `/api/v1/playback/video/{cam}/{file}` | `viewer` | Streams 30-second raw MP4 video recording segment. |

---

## 9. Captured Records Ledgers

Mounted at: `backend/routers/records.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/records/stats` | `viewer` | Aggregated count totals across faces, vehicles, license plates, OCR, scene captions, and global identities. |
| `GET` | `/api/v1/records/faces` | `viewer` | Paginated face sighting ledger (`?limit=50&offset=0&camera_id=...&search=...&sort=desc`). |
| `GET` | `/api/v1/records/vehicles` | `viewer` | Paginated vehicle sightings ledger with dominant colors and classifications. |
| `GET` | `/api/v1/records/plates` | `viewer` | Paginated license plate ledger filtered for verified OCR vehicle reads. |
| `GET` | `/api/v1/records/captions` | `viewer` | Paginated multimodal scene captions ledger generated by Florence-2 and Moondream 3.1. |
| `GET` | `/api/v1/records/ocr` | `viewer` | Paginated raw OCR text detection ledger. |
| `GET` | `/api/v1/florence/stats` | Public | Queue length and inference latency telemetry for Florence-2 scheduler. |

---

## 10. Forensics, Evidence & Trajectory

Mounted at: `backend/services/forensics.py`, `backend/services/trajectory.py`, `backend/services/co_occurrence.py`, `backend/services/fir_report.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `POST` | `/api/v1/forensics/export` | `operator` | Generates custom keyframe-aligned MP4 evidence clip, SHA-256 signature, and chain-of-custody package. |
| `GET` | `/api/v1/forensics/exports` | `viewer` | Lists all generated evidence export packages. |
| `GET` | `/api/v1/forensics/download/{filename}` | `viewer` | Downloads forensic evidence ZIP (path traversal protected via `safe_join_path`). |
| `GET` | `/api/v1/forensics/fir-report/{export_id}` | `operator` | Generates official HTML FIR Evidence Annexure with SHA-256 case integrity hash. |
| `GET` | `/api/v1/forensics/trajectory/{subject_id}` | `viewer` | Reconstructs multi-camera GPS trajectory route with chronological timeline cards. |
| `POST` | `/api/v1/forensics/trajectory-by-image` | `viewer` | Uploads face/target photograph and reconstructs cross-camera trajectory across all feeds. |
| `GET` | `/api/v1/forensics/co-occurrence` | `viewer` | Calculates single-camera spatial-temporal entity co-occurrence groups within a sliding time window. |
| `POST` | `/api/v1/forensics/co-occurrence/analyze` | `operator` | Executes cross-camera convoy/accomplice cluster analysis and generates candidate cluster entries. |
| `GET` | `/api/v1/forensics/co-occurrence/clusters`| `viewer` | Lists convoy/accomplice clusters with confidence scores and status. |
| `POST` | `/api/v1/forensics/co-occurrence/clusters/{cluster_uuid}/review` | `operator` | Submits investigator review (`CONFIRMED_CONVOY` vs `DISMISSED_FALSE_POSITIVE`). |

---

## 11. AI Skills Registry & Event Rules

Mounted at: `backend/routers/skills_rules.py` (FEAT-03)

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/skills` | `viewer` | Lists all registered AI skills (model name, FPS targets, hardware requirements, schemas). |
| `POST` | `/api/v1/skills` | `admin` | Registers a new AI skill in the global registry. |
| `PUT` | `/api/v1/skills/{skill_id}` | `admin` | Updates an existing AI skill definition. |
| `DELETE` | `/api/v1/skills/{skill_id}` | `admin` | Deletes skill and unassigns from all cameras. |
| `POST` | `/api/v1/skills/assign` | `admin` | Assigns an AI skill to a specific camera with parameter overrides. |
| `GET` | `/api/v1/skills/assignments` | `viewer` | Lists active camera-to-skill assignments (`?camera_id=...`). |
| `GET` | `/api/v1/event-rules` | `viewer` | Lists all declarative multi-condition event fusion rules. |
| `POST` | `/api/v1/event-rules` | `admin` | Creates a declarative event rule with condition logic and outbound actions (MQTT, Webhook, Email). |
| `PUT` | `/api/v1/event-rules/{rule_id}` | `admin` | Updates rule conditions, severity, cooldown, or actions. |
| `DELETE` | `/api/v1/event-rules/{rule_id}` | `admin` | Deletes a declarative event rule. |

---

## 12. POI & Stolen Vehicle Watchlists

Mounted at: `backend/services/watchlist/`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/watchlist` | `viewer` | Lists all registered Persons of Interest (POIs) with DPDP retention status labels. |
| `POST` | `/api/v1/watchlist` | `operator` | Enrolls new POI with reference photograph and generates 128d SFace / 512d ArcFace embeddings. |
| `POST` | `/api/v1/watchlist/purge-expired` | `admin` | Hard-deletes POI records older than 90 days in compliance with DPDP Act 2023. |
| `GET` | `/api/v1/watchlist/{uuid}/snapshot` | `viewer` | Serves POI face crop snapshot JPEG. |
| `GET` | `/api/v1/watchlist/stolen-vehicles` | `viewer` | Lists active stolen vehicle hot-list entries (CCTNS synchronized). |
| `POST` | `/api/v1/watchlist/stolen-vehicles` | `operator` | Adds a stolen/blacklisted vehicle plate to the hot-list. |

---

## 13. Analytics, Telemetry & Heatmaps

Mounted at: `backend/routers/analytics.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/analytics/heatmap` | `viewer` | Computes normalized 2D density heatmap coordinates `(x, y, value)` for a camera feed. |
| `GET` | `/api/v1/analytics/traffic-speed` | `viewer` | Returns speed distribution, vehicle flow rates, and directional metrics. |
| `GET` | `/api/v1/ai/status` | `viewer` | Detailed load state for YOLO, EasyOCR, SentenceTransformer, and Florence-2. |
| `GET` | `/api/v1/camera-telemetry` | `viewer` | Per-camera live ingestion frame rates, person counts, and worker status. |
| `GET` | `/api/v1/monitor/health` | `viewer` | Hardware vitals (CPU %, RAM %, GPU VRAM %, PostgreSQL, Qdrant). |

---

## 14. System Administration

Mounted at: `backend/admin/router.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/admin/users` | `admin` | Lists all user accounts (optional `?include_deleted=true`). |
| `POST` | `/api/v1/admin/users` | `admin` | Creates a new user account with role assignment and camera ACLs. |
| `PUT` | `/api/v1/admin/users/{id}` | `admin` | Modifies user role, status, password, or camera ACLs. |
| `DELETE` | `/api/v1/admin/users/{id}` | `admin` | Soft-deletes user account (sets `deleted_at` timestamp). |
| `POST` | `/api/v1/admin/users/{id}/hard-delete` | `admin` | Permanently erases user record (requires admin password re-authentication). |
| `GET` | `/api/v1/admin/audit-log` | `admin` | Paginated forensic audit log with action, username, and IP filtering. |

---

## 15. E-Challan & Citations

Mounted at: `backend/services/challan.py`

| Method | Endpoint | Minimum Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/challan/generate/{alert_id}` | `operator` | Generates official traffic violation citation HTML with embedded base64 QR code and SHA-256 verification signature. |

---

## 16. Infrastructure, Health & Metrics

Mounted at: `backend/main.py`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/healthz` | Public | Kubernetes liveness probe (returns HTTP 200 and epoch timestamp). |
| `GET` | `/readyz` | Public | Kubernetes readiness probe (verifies PostgreSQL connectivity; returns HTTP 503 if unavailable). |
| `GET` | `/metrics` | Public | Prometheus scrape endpoint returning system metrics in OpenMetrics text format. |
| `POST` | `/api/v1/bwc/live/register` | `operator` | Registers cellular Body-Worn Camera live WHEP/RTSP stream with GPS telemetry. |

---

## 17. WebSocket Real-Time Alert Stream

Mounted at: `/api/v1/ws/alerts` (`backend/main.py`)

### Connection Protocol
```text
ws://<server_host>:8000/api/v1/ws/alerts?token=<jwt_access_token>
```
Clients must provide a valid JWT access token in the `token` query parameter. The server validates token expiration, user status, and soft-delete state prior to accepting the handshake (closing with code `1008` if authentication fails).

### Payload Schema
```json
{
  "topic": "alerts",
  "data": {
    "type": "restricted",
    "event_uuid": "EVT_7c9a12e4",
    "camera_id": "cam_1",
    "message": "Restricted Area Entry: person detected in Zone Server Room",
    "severity": "high",
    "confidence": 0.95,
    "snapshot_url": "/api/v1/playback/snapshot/TRK_cam_1_42",
    "timestamp": "2026-08-16T17:05:00.123456+05:30"
  }
}
```
