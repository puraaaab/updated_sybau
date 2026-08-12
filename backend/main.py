import os
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;10000|reconnect;1|reconnect_streamed;1|reconnect_delay_max;5"

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session
from .database.connection import engine, SessionLocal, Base, get_db
from .database.models import Camera, AlertConfig
from .config import service as config_service
from .recording import recorder
from .workers import ai_worker
from .messaging.kafka_client import memory_bus

# Import sub-routers
from .auth.router import router as auth_router, _seed_users
from .admin.router import router as admin_router
from .services.watchlist import router as watchlist_router
from .services.forensics import router as forensics_router
from .services.trajectory import router as trajectory_router
from .services.co_occurrence import router as co_occurrence_router
from .services.fir_report import router as fir_report_router
from .services.challan import router as challan_router
from .routers.cameras import router as cameras_router
from .routers.playback import router as playback_router
from .routers.search import router as search_router
from .routers.analytics import router as analytics_router
from .routers.ptz import router as ptz_router
from .routers.records import router as records_router
from .routers.rules import router as rules_router
from .routers.proxy import router as proxy_router
from .routers.settings import router as settings_router

logging.getLogger("backend.ai.captioning.captioner").setLevel(logging.DEBUG)
logging.getLogger("backend.ai.model_manager").setLevel(logging.DEBUG)
logging.getLogger("backend.ai.pipeline.orchestrator").setLevel(logging.DEBUG)

active_websockets = []
main_loop = None


def broadcast_event_to_websockets(topic: str, data: dict):
    """
    Thread-safe broadcaster translating MemoryEventBus notifications to active WebSockets.
    Uses list copy to prevent mutation during iteration.
    """
    if not main_loop:
        return
    payload = {"topic": topic, "data": data}
    for ws in list(active_websockets):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(payload), main_loop)
        except Exception as e:
            print(f"Error forwarding event to WS: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()

    memory_bus.subscribe(broadcast_event_to_websockets)
    Base.metadata.create_all(bind=engine)

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS snapshot_url VARCHAR;"))
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS bbox TEXT;"))
            conn.execute(text("ALTER TABLE global_identities ADD COLUMN IF NOT EXISTS snapshot_path TEXT;"))
            conn.commit()
    except Exception as migration_e:
        print(f"Schema migration check note: {migration_e}")

    db = SessionLocal()
    try:
        if db.query(Camera).count() == 0:
            print("Seeding default cameras from cameras.json to database...")
            default_cams = config_service.get_cameras()
            for c in default_cams:
                db.add(Camera(
                    id=c["id"],
                    name=c["name"],
                    stream_url=c["stream_url"],
                    status="connecting",
                    width=c.get("width", 1920),
                    height=c.get("height", 1080)
                ))
            db.commit()

        if db.query(AlertConfig).count() == 0:
            print("Seeding default alert configurations...")
            cams = db.query(Camera).all()
            for cam in cams:
                db.add(AlertConfig(
                    camera_id=cam.id,
                    loitering_seconds=10,
                    running_speed_threshold=150.0,
                    crowd_density_threshold=5
                ))
            db.commit()

        _seed_users(db)
    finally:
        db.close()

    def _startup_ai():
        try:
            from .ai.scheduler import inference_scheduler
            inference_scheduler.start()

            from .ai.model_manager import model_manager
            print("Pre-warming YOLO, EasyOCR, and SentenceTransformer embedder on CUDA...")
            model_manager.get_yolo()
            model_manager.get_ocr()

            try:
                from .ai.embeddings.embedder import get_text_embedding
                get_text_embedding("prewarm vector search engine")
            except Exception as e:
                print(f"Note on SentenceTransformer pre-warm: {e}")

            try:
                from .search.qdrant_utils import get_qdrant_client
                get_qdrant_client()
            except Exception as e:
                print(f"Note on Qdrant pre-init: {e}")

            # Auto-create Kafka topics so a fresh Docker restart doesn't leave them missing.
            try:
                from kafka.admin import KafkaAdminClient, NewTopic
                _admin = KafkaAdminClient(bootstrap_servers="localhost:9092", request_timeout_ms=4000)
                _existing = set(_admin.list_topics())
                _needed = ["alerts", "captions", "tracks", "vehicles"]
                _to_create = [NewTopic(name=t, num_partitions=1, replication_factor=1)
                              for t in _needed if t not in _existing]
                if _to_create:
                    _admin.create_topics(_to_create, validate_only=False)
                    print(f"[Kafka] Auto-created topics: {[t.name for t in _to_create]}")
                _admin.close()
            except Exception as _ke:
                print(f"[Kafka] Topic auto-create note: {_ke}")

            print("Starting background Stream Recorders and AI Workers...")
            recorder.start_all_recorders()
            ai_worker.start_all_ai_workers()

            from .ai.captioning.moondream_captioner import start_moondream_worker
            start_moondream_worker()

            from .recording.retention import retention_manager
            retention_manager.start()

            # Florence pre-warm runs LAST and in its own thread so it never blocks
            # YOLO inference. Florence-2-large takes ~70s to load on first call;
            # without this delay the CUDA RLock monopolises the GPU and YOLO can't
            # write any records until Florence finishes its first generate() call.
            def _delayed_florence_prewarm():
                import time as _t
                _t.sleep(5)  # Let YOLO process a few frames first
                from .ai.captioning.captioner import pre_warm as pre_warm_captioner
                pre_warm_captioner()
            threading.Thread(target=_delayed_florence_prewarm, daemon=True, name="Florence_Prewarm").start()

        except Exception as _startup_exc:
            import traceback
            print(f"[FATAL] AI startup thread crashed: {_startup_exc}")
            traceback.print_exc()

    threading.Thread(target=_startup_ai, daemon=True, name="AI_Startup").start()

    yield

    print("Shutting down background workers...")
    recorder.stop_all_recorders()
    ai_worker.stop_all_ai_workers()

    from .recording.retention import retention_manager
    retention_manager.stop()

    from .ai.scheduler import inference_scheduler
    inference_scheduler.stop()


app = FastAPI(
    title="VMS AI Surveillance Platform",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "*")
if os.getenv("APP_ENV") == "production":
    if not _cors_origins_env or _cors_origins_env == "*":
        raise RuntimeError("FATAL: CORS_ALLOWED_ORIGINS must be set in production mode and cannot be '*'!")
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",")]
else:
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",")] if _cors_origins_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all sub-routers cleanly under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(watchlist_router, prefix="/api/v1")
app.include_router(forensics_router, prefix="/api/v1")
app.include_router(trajectory_router, prefix="/api/v1")
app.include_router(co_occurrence_router, prefix="/api/v1")
app.include_router(fir_report_router, prefix="/api/v1")
app.include_router(challan_router, prefix="/api/v1")
app.include_router(cameras_router, prefix="/api/v1")
app.include_router(playback_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(ptz_router, prefix="/api/v1")
app.include_router(records_router, prefix="/api/v1")
app.include_router(rules_router, prefix="/api/v1")
app.include_router(proxy_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
from .routers.copilot import router as copilot_router
app.include_router(copilot_router, prefix="/api/v1")


from fastapi.responses import PlainTextResponse
from .monitoring.metrics import generate_prometheus_metrics
from .monitoring.health import get_services_health
from .services.bwc_live_ingest import bwc_live_ingest_service

@app.get("/healthz", tags=["Infrastructure"])
def liveness_probe():
    """Kubernetes Liveness Probe."""
    return {"status": "ok", "timestamp": time.time()}

@app.get("/readyz", tags=["Infrastructure"])
def readiness_probe():
    """Kubernetes Readiness Probe checking DB and internal services."""
    services = get_services_health()
    is_ready = services.get("postgresql") == "online"
    if not is_ready:
        return PlainTextResponse(content="Service Not Ready", status_code=503)
    return {"status": "ready", "services": services}

@app.get("/metrics", tags=["Infrastructure"])
def prometheus_metrics_endpoint():
    """Scraping endpoint for Prometheus monitoring systems."""
    return PlainTextResponse(generate_prometheus_metrics(), media_type="text/plain")

@app.post("/api/v1/bwc/live/register", tags=["BodyWornCameras"])
def register_bwc_live_stream(
    officer_id: str,
    badge_number: str,
    device_serial: str,
    lat: float = None,
    lng: float = None,
    db: Session = Depends(get_db)
):
    """Registers an active cellular live Body-Worn Camera stream."""
    return bwc_live_ingest_service.register_live_bwc(
        db=db,
        officer_id=officer_id,
        badge_number=badge_number,
        device_serial=device_serial,
        lat=lat,
        lng=lng
    )


@app.websocket("/api/v1/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    # BUG-16 FIX: Validate JWT before accepting the WebSocket connection.
    # Clients must pass ?token=<jwt> in the connection URL.
    from .auth.helpers import SECRET_KEY, ALGORITHM
    import jwt as _jwt
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return
    try:
        _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired authentication token")
        return

    await websocket.accept()
    active_websockets.append(websocket)
    print(f"New client connected to alerts WebSocket. Active clients: {len(active_websockets)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        print("Alerts WebSocket client disconnected.")

