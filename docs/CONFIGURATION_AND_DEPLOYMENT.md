# Configuration & Deployment Guide — Sybau VMS Pro

> **Comprehensive operational guide to environment configuration, JSON configs, Docker containerization, Windows PowerShell commands, and production deployment.**

---

## Table of Contents
1. [Environment Variables Catalog](#1-environment-variables-catalog)
2. [JSON Configuration Files](#2-json-configuration-files)
3. [Docker & Container Infrastructure](#3-docker--container-infrastructure)
4. [Windows Management (`manage.ps1`)](#4-windows-management-manageps1)
5. [Linux & Manual Production Startup](#5-linux--manual-production-startup)
6. [Kubernetes Health Probes & Prometheus Scraping](#6-kubernetes-health-probes--prometheus-scraping)
7. [Default Ports & Access Endpoints](#7-default-ports--access-endpoints)

---

## 1. Environment Variables Catalog

Configured in `.env` (derived from `.env.example`):

| Variable | Default Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://vms_user:vms_password@localhost:5432/vms_db` | SQLAlchemy PostgreSQL connection DSN. SQLite fallback: `sqlite:///./vms.db`. |
| `VMS_SECRET_KEY` / `SECRET_KEY` | *(Secret String)* | Cryptographic key for JWT HS256 token signing. Must be explicitly set in production. |
| `ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT token validity lifetime (default: 8 hours). |
| `APP_ENV` | `development` | Setting to `production` enforces non-wildcard CORS and strict secret keys. |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated list of allowed web origins (cannot be `*` in production). |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker endpoints. |
| `USE_MEMORY_BUS_ONLY` | `false` | When `true`, skips Kafka and routes events through the internal `MemoryEventBus`. |
| `QDRANT_HOST` | `localhost` | Qdrant vector database host. |
| `QDRANT_PORT` | `6333` | Qdrant HTTP API port. |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO S3 object storage endpoint. |
| `MINIO_ROOT_USER` | `minio_admin` | MinIO S3 access key ID. |
| `MINIO_ROOT_PASSWORD` | `minio_password` | MinIO S3 secret access key. |
| `MINIO_SECURE` | `false` | Enable HTTPS for MinIO client requests. |
| `INITIAL_ADMIN_PASSWORD` | `Admin@123456` | Default administrator password seeded during first-time database initialization. |
| `MOONDREAM_API_KEY` | `""` | Primary Moondream 3.1 VLM API key. |
| `MOONDREAM_API_KEYS` | `""` | Comma-separated API key pool for round-robin cloud captioning. |
| `MOONDREAM_MODEL` | `moondream3.1-9B-A2B` | Moondream vision-language model target name. |

---

## 2. JSON Configuration Files

Located in the `configs/` directory and loaded via `backend/config/service.py`:

### 2.1 `configs/models.json`
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
    "enabled": false,
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

### 2.2 `configs/alerts.json`
```json
{
  "cooldown_seconds": 30.0,
  "loitering": { "enabled": true, "time_threshold_seconds": 10.0 },
  "running": { "enabled": true, "speed_threshold_pixels_per_second": 150.0 },
  "crowd": { "enabled": true, "density_threshold": 5 },
  "restricted": { "enabled": true },
  "wrong_direction": { "enabled": false },
  "abandoned": { "enabled": true, "dwell_time_sec": 60.0, "owner_distance_pixels": 150.0 }
}
```

### 2.3 `configs/privacy.json`
```json
{
  "enabled": false,
  "redact_faces": true,
  "redact_plates": true,
  "blur_kernel_size": 51,
  "mode": "FULL_REDACTION"
}
```

### 2.4 `configs/zones.json`
Normalized polygon boundaries (`[x, y]` values between 0.0 and 1.0):
```json
[
  {
    "camera_id": "cam_1",
    "type": "restricted",
    "name": "Server Room Perimeter",
    "points": [[0.1, 0.2], [0.45, 0.2], [0.45, 0.8], [0.1, 0.8]]
  }
]
```

---

## 3. Docker & Container Infrastructure

### 3.1 Docker Compose Services (`docker-compose.yml`)

```yaml
services:
  postgres:
    image: postgres:15
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: vms_user
      POSTGRES_PASSWORD: vms_password
      POSTGRES_DB: vms_db

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]

  mediamtx:
    image: bluenviron/mediamtx
    ports: ["8554:8554", "8888:8888", "8889:8889"]

  minio:
    image: minio/minio:latest
    ports: ["9000:9000", "9001:9001"]
    command: server /data --console-address ":9001"

  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.0
    ports: ["2181:2181"]

  kafka:
    image: confluentinc/cp-kafka:7.6.0
    ports: ["9092:9092"]
```

### 3.2 Backend Dockerfile (`Dockerfile.backend`)
Multi-stage build based on `python:3.10-slim`:
- Installs OpenCV and FFmpeg runtime dependencies (`libgl1`, `libglib2.0-0`, `ffmpeg`, `libpq-dev`).
- Installs Python wheels from `requirements.txt`.
- Runs Uvicorn ASGI server on port 8000.

### 3.3 Frontend Dockerfile (`Dockerfile.frontend`) & Nginx
- **Build Stage**: Node.js 20 Alpine compiles React 19 bundles via `npm run build`.
- **Nginx Stage**: Serves compiled static assets, providing reverse-proxy paths:
  - `/api/` $\rightarrow$ `http://backend:8000/api/`
  - `/ws/` $\rightarrow$ `http://backend:8000/ws/` with WebSocket connection upgrade headers.

---

## 4. Windows Management (`manage.ps1`)

The repository includes a PowerShell orchestration script:

```powershell
# Start all infrastructure, backend, frontend, and emulator services:
.\manage.ps1 start

# Stop all running services:
.\manage.ps1 stop

# Restart all services:
.\manage.ps1 restart
```

### Script Execution Sequence (`manage.ps1 start`)
1. Creates local `logs/` and `storage/` directories.
2. Launches background Docker services: `postgres`, `qdrant`, `mediamtx`, `minio`, `zookeeper`, `kafka`.
3. Runs database migrations via `backend/database/migrations/runner.py`.
4. Starts FastAPI backend with Uvicorn on port 8000.
5. Starts Vite frontend on port 5173.
6. Starts NVR RTSP video emulator.
7. Polls `/docs` until backend is fully operational.

---

## 5. Linux & Manual Production Startup

```bash
# 1. Start database & vector services
docker compose up -d postgres qdrant mediamtx minio kafka

# 2. Activate Python environment & run migrations
source .venv/bin/activate
python -m backend.database.migrations.runner

# 3. Start Backend Uvicorn Server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1

# 4. Build and serve Frontend
cd frontend
npm ci
npm run build
```

---

## 6. Kubernetes Health Probes & Prometheus Scraping

- **Liveness Probe (`GET /healthz`)**: Returns HTTP 200 and epoch timestamp.
- **Readiness Probe (`GET /readyz`)**: Pings PostgreSQL database; returns HTTP 503 if database connectivity fails.
- **Prometheus Metrics (`GET /metrics`)**: Returns OpenMetrics formatted telemetry:
  - `vms_active_cameras_total`
  - `vms_ingestion_fps_current`
  - `vms_alerts_emitted_total`
  - `vms_gpu_vram_used_bytes`

---

## 7. Default Ports & Access Endpoints

| Service | Port | Endpoint |
|---|---|---|
| Frontend Web Console | `5173` | `http://localhost:5173` |
| Backend FastAPI / Swagger | `8000` | `http://localhost:8000/docs` |
| Qdrant Vector Dashboard | `6333` | `http://localhost:6333/dashboard` |
| MinIO Storage Console | `9001` | `http://localhost:9001` |
| MediaMTX HLS Streams | `8888` | `http://localhost:8888/{camera_id}/index.m3u8` |
| MediaMTX WebRTC (WHEP) | `8889` | `http://localhost:8889/{camera_id}/whep` |
| Apache Kafka Broker | `9092` | `localhost:9092` |
| PostgreSQL Database | `5432` | `localhost:5432` |
