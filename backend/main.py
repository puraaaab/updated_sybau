import os

# Set OpenCV environment variables BEFORE any cv2 import happens across modules
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;10000|reconnect;1|reconnect_streamed;1|reconnect_delay_max;5"

import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database.connection import engine, get_db, SessionLocal, Base
from .database.models import Alert, Camera, Zone, AlertConfig, GlobalIdentity, Vehicle, Track, Face, SceneCaption
from .auth.router import router as auth_router
from .admin.router import router as admin_router
from .services.watchlist import router as watchlist_router
from .services.forensics import router as forensics_router
from .services.trajectory import router as trajectory_router
from .services.co_occurrence import router as co_occurrence_router
from .services.fir_report import router as fir_report_router
from .services.challan import router as challan_router
from .auth.helpers import verify_admin, verify_operator, verify_viewer, verify_media_access
from .config import service as config_service
from .config.service import get_models
from .recording import recorder
from .workers import ai_worker
from .monitoring import health as monitoring_health
from .services import event_export
from .search import vector_search
from .messaging.kafka_client import memory_bus
from .utils.security import safe_join_path
from .utils.ssrf import validate_proxy_url

# ---------------------------------------------------------------------------
# Lifespan context manager (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

# WebSocket connection manager
active_websockets = []
main_loop = None


def broadcast_event_to_websockets(topic: str, data: dict):
    """
    Thread-safe broadcaster translating MemoryEventBus notifications to active WebSockets.
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

    # Register memory event bus callback for WS broadcasting
    memory_bus.subscribe(broadcast_event_to_websockets)

    # Create all DB tables (Postgres or SQLite fallback) on start
    Base.metadata.create_all(bind=engine)

    # Seed default databases if empty
    db = SessionLocal()
    try:
        # Check if cameras table is empty
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

        # Seed default alert configs
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

        # Seed initial users if empty
        from .auth.router import _seed_users
        _seed_users(db)
    finally:
        db.close()

    def _startup_ai():
        try:
            # Pre-warm Florence-2 in its own sub-thread so it doesn't block worker startup
            from .ai.captioning.captioner import pre_warm as pre_warm_captioner
            import threading as _threading
            _threading.Thread(target=pre_warm_captioner, daemon=True, name="Florence_Prewarm").start()

            from .ai.model_manager import model_manager
            # Also pre-warm other heavy models to ensure smooth worker startup
            print("Pre-warming YOLO, EasyOCR, and SentenceTransformer embedder...")
            model_manager.get_yolo()
            model_manager.get_ocr()
            try:
                from .ai.embeddings.embedder import get_text_embedding
                get_text_embedding("prewarm vector search engine")
                print("SentenceTransformer text embedder pre-warmed for ultra-fast forensic query response.")
            except Exception as e:
                print(f"Note on SentenceTransformer pre-warm: {e}")

            try:
                from .ai.person.person_attribute_engine import _get_clip_model
                _get_clip_model()
                print("OpenCLIP vision-language embedder pre-warmed for ultra-fast person crop feature extraction.")
            except Exception as e:
                print(f"Note on OpenCLIP pre-warm: {e}")

            try:
                from .search.qdrant_utils import get_qdrant_client
                get_qdrant_client()
                print("Qdrant Vector DB collection verified and batch worker thread active.")
            except Exception as e:
                print(f"Note on Qdrant pre-init: {e}")

            from .ai.scheduler import inference_scheduler
            inference_scheduler.start()

            # Start continuous recording and AI threads only after the inference
            # scheduler is live; otherwise camera workers can block on their first
            # GPU task during startup.
            print("Starting background Stream Recorders and AI Workers...")
            recorder.start_all_recorders()
            ai_worker.start_all_ai_workers()

            from .recording.retention import retention_manager
            retention_manager.start()
        except Exception as _startup_exc:
            import traceback
            print(f"[FATAL] AI startup thread crashed: {_startup_exc}")
            traceback.print_exc()

    # Start the AI subsystem in a background thread so the FastAPI server
    # can bind to port 8000 immediately without blocking `manage.ps1`
    import threading
    threading.Thread(target=_startup_ai, daemon=True, name="AI_Startup").start()

    yield  # Application runs here

    # --- Shutdown ---
    print("Shutting down background workers...")
    recorder.stop_all_recorders()
    ai_worker.stop_all_ai_workers()

    from .recording.retention import retention_manager
    retention_manager.stop()

    from .ai.scheduler import inference_scheduler
    inference_scheduler.stop()


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VMS AI Surveillance Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — lock to specific origins in production via env var
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

# Include Authentication Router
app.include_router(auth_router, prefix="/api/v1")

# Include Admin Router
app.include_router(admin_router, prefix="/api/v1")

# Include Watchlist, Forensics, Trajectory, CoOccurrence & FIR Report Routers
app.include_router(watchlist_router, prefix="/api/v1")
app.include_router(forensics_router, prefix="/api/v1")
app.include_router(trajectory_router, prefix="/api/v1")
app.include_router(co_occurrence_router, prefix="/api/v1")
app.include_router(fir_report_router, prefix="/api/v1")
app.include_router(challan_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/api/v1/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    print(f"New client connected to alerts WebSocket. Active clients: {len(active_websockets)}")
    try:
        while True:
            # Keep connection alive — client sends periodic pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        print("Alerts WebSocket client disconnected.")


# ---------------------------------------------------------------------------
# Camera Management API
# ---------------------------------------------------------------------------

@app.get("/api/v1/cameras")
def get_cameras(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    cams = db.query(Camera).all()
    result = []
    from .services.stream_resolver import resolve_stream_url
    for c in cams:
        telem = ai_worker.latest_telemetry.get(c.id, {})
        cam_dict = {
            "id": c.id,
            "name": c.name,
            "location": c.location or "Unknown",
            "stream_url": c.stream_url,
            "status": c.status,
            "width": c.width,
            "height": c.height,
            "motion_status": telem.get("motion_status", "STREAMING"),
            "fps": telem.get("fps", 2.0)
        }
        # Always serve /hls/{cam_id}/index.m3u8 to the browser.
        # The backend workers (OpenCV / stream_manager) consume the raw source
        # (local file, RTSP, YouTube) internally. MediaMTX then publishes the
        # transcoded stream as HLS. Returning raw file:// paths crashes HLS.js.
        raw = c.stream_url or ""
        is_youtube = "youtube.com" in raw or "youtu.be" in raw
        if is_youtube:
            cam_dict["hls_url"] = raw  # YouTube streams are rendered via iframe
            cam_dict["is_youtube"] = True
        else:
            cam_dict["hls_url"] = f"http://localhost:8888/{c.id}/index.m3u8"
            cam_dict["is_youtube"] = False
        result.append(cam_dict)
    return result


@app.post("/api/v1/cameras/scan")
def scan_onvif_cameras(user=Depends(verify_viewer)):
    """
    Scans the local subnet using WS-Discovery on UDP 3702 for ONVIF IP Cameras & NVRs.
    Performs real multicast socket probe and falls back to simulated endpoints if no physical camera responds.
    """
    import socket
    ws_probe = """<?xml version="1.0" encoding="UTF-8"?>
    <e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
                xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
                xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
      <e:Header>
        <w:MessageID>uuid:84576391-4b3e-4c72-91ef-75210214a1a0</w:MessageID>
        <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
        <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
      </e:Header>
      <e:Body>
        <d:Probe>
          <d:Types>dn:NetworkVideoTransmitter</d:Types>
        </d:Probe>
      </e:Body>
    </e:Envelope>"""
    
    discovered_real = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(1.5)
        sock.sendto(ws_probe.encode('utf-8'), ('239.255.255.250', 3702))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if not any(d['ip'] == ip for d in discovered_real):
                    discovered_real.append({
                        "name": f"ONVIF Camera ({ip})",
                        "ip": ip,
                        "port": 80,
                        "mac": f"00:1A:2B:3C:4D:{len(discovered_real)+1:02d}"
                    })
            except socket.timeout:
                break
        sock.close()
    except Exception as e:
        print("WS-Discovery scan note:", e)

    # Use real discovered devices if found, otherwise return demo fallback if demo_mode is enabled
    devices = discovered_real
    if len(devices) == 0:
        cfg = get_models()
        if cfg.get("demo_mode", False):
            devices = [
                {"name": "Hikvision NVR Channel 1", "ip": "192.168.1.101", "port": 80, "mac": "00:1A:2B:3C:4D:01"},
                {"name": "Dahua Body-Worn Cam Relay", "ip": "192.168.1.102", "port": 80, "mac": "00:1A:2B:3C:4D:02"},
                {"name": "Axis Dome Camera P3245", "ip": "192.168.1.103", "port": 80, "mac": "00:1A:2B:3C:4D:03"},
                {"name": "CP PLUS Speed Dome", "ip": "192.168.1.104", "port": 80, "mac": "00:1A:2B:3C:4D:04"}
            ]
    return {"status": "success", "count": len(devices), "is_real": len(discovered_real) > 0, "devices": devices}


@app.post("/api/v1/cameras/resolve-onvif")
def resolve_onvif_stream_uri(payload: dict, user=Depends(verify_viewer)):
    """
    Resolves ONVIF media profile RTSP URI using provided device credentials.
    Attempts real ONVIF SOAP Media Service GetStreamUri probe first, falling back to standard RTSP pattern.
    """
    ip = payload.get("onvif_ip", "127.0.0.1")
    port = payload.get("onvif_port", 80)
    uname = payload.get("onvif_username", "admin")
    pwd = payload.get("onvif_password", "")
    
    rtsp_url = f"rtsp://{uname}:{pwd}@{ip}:554/live/ch0" if pwd else f"rtsp://{ip}:554/live/ch0"
    is_real = False

    try:
        from onvif import ONVIFCamera
        mycam = ONVIFCamera(ip, port, uname, pwd)
        media_service = mycam.create_media_service()
        profiles = media_service.GetProfiles()
        if profiles:
            token = profiles[0].token
            obj = media_service.create_type('GetStreamUri')
            obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
            obj.ProfileToken = token
            res = media_service.GetStreamUri(obj)
            if res and hasattr(res, 'Uri'):
                rtsp_url = res.Uri
                is_real = True
    except Exception as e:
        # Fallback to direct RTSP URI string construction
        pass

    return {
        "status": "success",
        "onvif_ip": ip,
        "stream_url": rtsp_url,
        "is_real_soap": is_real
    }


@app.post("/api/v1/cameras")
def add_camera(camera: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    existing = db.query(Camera).filter(Camera.id == camera["id"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="Camera ID already exists")

    new_cam = Camera(
        id=camera["id"],
        name=camera["name"],
        location=camera.get("location", "Unknown"),
        stream_url=camera["stream_url"],
        status="connecting",
        width=camera.get("width", 1920),
        height=camera.get("height", 1080)
    )
    db.add(new_cam)

    # Initialize default alert thresholds for this camera
    default_cfg = AlertConfig(
        camera_id=camera["id"],
        loitering_seconds=10,
        running_speed_threshold=150.0,
        crowd_density_threshold=5
    )
    db.add(default_cfg)
    db.commit()

    # Dynamically spawn workers for the new camera
    if camera["id"] not in recorder.active_recorders:
        rec = recorder.CameraRecorder(camera["id"], camera["stream_url"])
        recorder.active_recorders[camera["id"]] = rec
        rec.start()

    if camera["id"] not in ai_worker.active_ai_workers:
        worker = ai_worker.CameraAIWorker(camera["id"], camera["stream_url"])
        ai_worker.active_ai_workers[camera["id"]] = worker
        worker.start()

    return {"message": "Camera added and workers spawned successfully"}


@app.put("/api/v1/cameras/{camera_id}")
def update_camera(camera_id: str, camera: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    old_url = cam.stream_url
    cam.name = camera.get("name", cam.name)
    cam.location = camera.get("location", cam.location)
    cam.stream_url = camera.get("stream_url", cam.stream_url)
    cam.width = camera.get("width", cam.width)
    cam.height = camera.get("height", cam.height)
    
    db.commit()
    db.refresh(cam)

    if old_url != cam.stream_url:
        # Tear down old workers and restart
        if camera_id in recorder.active_recorders:
            recorder.active_recorders[camera_id].stop()
            del recorder.active_recorders[camera_id]
        if camera_id in ai_worker.active_ai_workers:
            ai_worker.active_ai_workers[camera_id].stop()
            del ai_worker.active_ai_workers[camera_id]
            
        rec = recorder.CameraRecorder(camera_id, cam.stream_url)
        recorder.active_recorders[camera_id] = rec
        rec.start()

        worker = ai_worker.CameraAIWorker(camera_id, cam.stream_url)
        ai_worker.active_ai_workers[camera_id] = worker
        worker.start()
        
    return {"message": "Camera updated successfully"}


@app.delete("/api/v1/cameras/{camera_id}")
def delete_camera(camera_id: str, user=Depends(verify_admin), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Delete associated zones and configs
    db.query(Zone).filter(Zone.camera_id == camera_id).delete()
    db.query(AlertConfig).filter(AlertConfig.camera_id == camera_id).delete()
    db.delete(cam)
    db.commit()

    # Tear down camera threads
    if camera_id in recorder.active_recorders:
        recorder.active_recorders[camera_id].stop()
        del recorder.active_recorders[camera_id]

    if camera_id in ai_worker.active_ai_workers:
        ai_worker.active_ai_workers[camera_id].stop()
        del ai_worker.active_ai_workers[camera_id]

    return {"message": "Camera removed successfully"}


# ---------------------------------------------------------------------------
# Zones API
# ---------------------------------------------------------------------------

@app.get("/api/v1/cameras/{camera_id}/zones")
def get_camera_zones(camera_id: str, user=Depends(verify_viewer), db: Session = Depends(get_db)):
    zones = db.query(Zone).filter(Zone.camera_id == camera_id).all()
    import json
    return [
        {
            "id": z.id,
            "camera_id": z.camera_id,
            "type": z.type,
            "name": z.name,
            "points": json.loads(z.points),
            "direction_vector": json.loads(z.direction_vector) if z.direction_vector else None
        } for z in zones
    ]


@app.post("/api/v1/cameras/{camera_id}/zones")
def save_camera_zones(camera_id: str, zones: list, user=Depends(verify_admin), db: Session = Depends(get_db)):
    import json
    db.query(Zone).filter(Zone.camera_id == camera_id).delete()

    for z in zones:
        points_data = z.get("points", [])
        dir_vec = z.get("direction_vector", None)

        new_zone = Zone(
            camera_id=camera_id,
            type=z.get("type", "restricted"),
            name=z.get("name", "Zone"),
            points=json.dumps(points_data),
            direction_vector=json.dumps(dir_vec) if dir_vec else None
        )
        db.add(new_zone)

    db.commit()
    return {"message": "Camera zones saved successfully"}


# ---------------------------------------------------------------------------
# Alerts History API
# ---------------------------------------------------------------------------

@app.get("/api/v1/alerts")
def get_alerts_history(db: Session = Depends(get_db), user=Depends(verify_viewer)):
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).limit(100).all()
    return alerts


@app.post("/api/v1/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), user=Depends(verify_operator)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_acknowledged = True
    db.commit()
    return {"message": "Alert acknowledged"}


@app.get("/api/v1/alerts/{alert_id}/export")
def download_forensic_export(alert_id: int, db: Session = Depends(get_db), user=Depends(verify_operator)):
    try:
        zip_path = event_export.export_alert_evidence(alert_id, db)
        return FileResponse(zip_path, media_type="application/zip", filename=os.path.basename(zip_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Playback & Video Archive API
# ---------------------------------------------------------------------------

@app.get("/api/v1/playback/snapshot/{snap_id}")
def serve_snapshot(snap_id: str, user=Depends(verify_media_access)):
    snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "snapshots"))
    
    # Try exact match, with .jpg extension, or without extension
    candidates = [
        safe_join_path(snap_dir, f"{snap_id}.jpg"),
        safe_join_path(snap_dir, snap_id),
    ]
    if not snap_id.endswith(".jpg"):
        candidates.append(safe_join_path(snap_dir, f"{snap_id}.png"))
        
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="image/jpeg")
            
    raise HTTPException(status_code=404, detail="Snapshot not found")


@app.get("/api/v1/playback/timeline/{camera_id}")
def get_timeline_clips(camera_id: str, user=Depends(verify_viewer)):
    rec_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "recordings"))
    cam_rec_dir = safe_join_path(rec_base_dir, camera_id)
    if not os.path.exists(cam_rec_dir):
        return []
    files = sorted(os.listdir(cam_rec_dir))
    return [{"filename": f, "filepath": f"/api/v1/playback/video/{camera_id}/{f}"} for f in files if f.endswith(".mp4")]


@app.get("/api/v1/playback/video/{camera_id}/{clip_name}")
def serve_video_clip(camera_id: str, clip_name: str, user=Depends(verify_media_access)):
    rec_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "recordings"))
    video_path = safe_join_path(rec_base_dir, camera_id, clip_name)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video clip not found")
    return FileResponse(video_path, media_type="video/mp4")



# ---------------------------------------------------------------------------
# System Health API
# ---------------------------------------------------------------------------

@app.get("/api/v1/monitor/health")
def get_health(user=Depends(verify_viewer)):
    return monitoring_health.get_full_health_report()


@app.get("/api/v1/ai/status")
def get_ai_status(user=Depends(verify_viewer)):
    """
    Returns real-time initialization status of all AI models.
    """
    from .ai.model_manager import model_manager
    from .ai.embeddings.embedder import _sentence_transformer_model

    models = model_manager._models
    yolo_loaded = "yolo" in models
    ocr_loaded = "ocr" in models
    florence_loaded = "florence" in models
    embedder_loaded = _sentence_transformer_model is not None

    all_ready = yolo_loaded and embedder_loaded

    return {
        "status": "READY" if all_ready else "PREWARMING",
        "all_ready": all_ready,
        "models": {
            "YOLO26m": "LOADED" if yolo_loaded else "LOADING",
            "OCR": "LOADED" if ocr_loaded else "LOADING",
            "Embedder": "LOADED" if embedder_loaded else "LOADING",
            "Florence": "LOADED" if florence_loaded else "LOADING"
        }
    }


# ---------------------------------------------------------------------------
# Search API (Semantic + Face Vector Similarity)
# ---------------------------------------------------------------------------

@app.get("/api/v1/search/semantic")
def search_semantic(
    q: str = Query(..., min_length=1), 
    limit: int = Query(default=10),
    start_time: str = Query(default=None),
    end_time: str = Query(default=None),
    user=Depends(verify_viewer)
):
    results = vector_search.perform_semantic_search(q, limit=limit, start_time=start_time, end_time=end_time)
    return results


@app.get("/api/v1/search/license-plate")
def search_license_plate(q: str = Query(..., min_length=1), limit: int = Query(default=50), db: Session = Depends(get_db), user=Depends(verify_viewer)):
    search_query = f"%{q.strip().upper()}%"
    results = db.query(Vehicle).filter(
        Vehicle.license_plate.like(search_query)
    ).order_by(
        Vehicle.timestamp.desc()
    ).limit(limit).all()
    
    # Resolve camera names
    camera_map = {cam.id: cam.name for cam in db.query(Camera).all()}
    
    return [
        {
            "id": vehicle.id,
            "license_plate": vehicle.license_plate,
            "ocr_confidence": vehicle.ocr_confidence,
            "vehicle_type": vehicle.vehicle_type,
            "timestamp": vehicle.timestamp,
            "track_uuid": vehicle.track_uuid,
            "camera_id": vehicle.camera_id or "Unknown",
            "camera_name": camera_map.get(vehicle.camera_id, "Unknown") if vehicle.camera_id else "Unknown"
        } for vehicle in results
    ]


@app.get("/api/v1/search/debug")
def debug_search(user=Depends(verify_viewer)):
    from .ai.model_manager import model_manager
    cfg = get_models()
    return {
        "vector_db_len": len(model_manager.vector_db),
        "demo_mode": cfg.get("demo_mode", False),
        "module_id": id(model_manager),
        "qdrant_status": "OFFLINE",
        "snapshots_dir_count": len(os.listdir(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "snapshots"))
        )) if os.path.exists(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "snapshots"))
        ) else 0
    }


@app.post("/api/v1/search/face")
async def search_face(
    file: UploadFile = File(...), 
    start_time: str = Query(default=None),
    end_time: str = Query(default=None),
    user=Depends(verify_viewer)
):
    import numpy as np
    import cv2
    from .ai.face import face_pipeline

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode image format. Upload a valid JPG/PNG file.")

    h, w = img.shape[:2]
    try:
        detector, recognizer = face_pipeline.get_face_models(w, h)
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)

        if faces is not None and len(faces) > 0:
            aligned_face = recognizer.alignCrop(img, faces[0])
            embedding = recognizer.feature(aligned_face).flatten().tolist()
            results = vector_search.perform_face_search(embedding, start_time=start_time, end_time=end_time)
            return results
        else:
            raise HTTPException(status_code=422, detail="No face detected in uploaded image. Please provide a clear face snapshot.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Face embedding pipeline error: {str(e)}")


# ---------------------------------------------------------------------------
# Settings API
# ---------------------------------------------------------------------------

@app.get("/api/v1/settings")
def get_settings(user=Depends(verify_viewer)):
    return {
        "alerts": config_service.get_alerts(),
        "models": config_service.get_models()
    }


@app.post("/api/v1/settings/alerts")
def save_alerts_settings(settings: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    from .utils.audit import log_audit_event
    config_service.save_alerts(settings)
    log_audit_event(db, action="SETTINGS_UPDATE", detail="Updated alert thresholds", username=user.username)
    return {"message": "Alert thresholds updated"}


@app.post("/api/v1/settings/models")
def save_models_settings(settings: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    from .utils.audit import log_audit_event
    config_service.save_models(settings)
    log_audit_event(db, action="SETTINGS_UPDATE", detail="Updated model configurations", username=user.username)
    return {"message": "Model settings updated"}


# ---------------------------------------------------------------------------
# Camera Stream Resolution (uses shared StreamResolver)
# ---------------------------------------------------------------------------

import time
from .services.stream_resolver import resolve_stream_url, is_youtube_url


@app.get("/api/v1/cameras/{camera_id}/stream")
def get_camera_resolved_stream(camera_id: str, request: Request, user=Depends(verify_viewer), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    original_url = cam.stream_url

    # For local video clip files (.avi, .mp4, etc.), route through MJPEG live stream generator
    if os.path.exists(original_url) or original_url.lower().endswith((".avi", ".mp4", ".mkv", ".mov")):
        base_url = str(request.base_url).rstrip("/")
        mjpeg_url = f"{base_url}/api/v1/cameras/{camera_id}/mjpeg"
        return {"stream_url": mjpeg_url, "is_hls": False}

    resolved = resolve_stream_url(camera_id, original_url)

    if not resolved:
        return {"stream_url": original_url, "is_hls": False}

    # For YouTube-resolved URLs, wrap through the CORS proxy for browser playback
    if is_youtube_url(original_url) and resolved != original_url:
        import urllib.parse
        base_url = str(request.base_url).rstrip("/")
        proxied_url = f"{base_url}/api/v1/proxy/m3u8?url={urllib.parse.quote_plus(resolved)}"
        return {"stream_url": proxied_url, "is_hls": True}

    # Intercept internal RTSP streams and route them to MediaMTX's HLS endpoint.
    if resolved.startswith("rtsp://127.0.0.1:8554/") or resolved.startswith("rtsp://localhost:8554/"):
        cam_id = resolved.split("/")[-1]
        hls_url = f"http://localhost:8888/{cam_id}/index.m3u8"
        return {"stream_url": hls_url, "is_hls": True}

    return {"stream_url": resolved, "is_hls": False}


@app.get("/api/v1/cameras/{camera_id}/mjpeg")
def stream_camera_mjpeg(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    stream = stream_manager.get_stream(camera_id, cam.stream_url)

    def generate():
        while True:
            success, frame, _ = stream.get_frame()
            if success and frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.04)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---------------------------------------------------------------------------
# YouTube HLS CORS Bypass Proxy
# ---------------------------------------------------------------------------

import httpx
import urllib.parse
from fastapi.responses import Response, StreamingResponse


@app.get("/api/v1/proxy/m3u8")
async def proxy_m3u8(url: str, request: Request, user=Depends(verify_viewer)):
    validated_url = validate_proxy_url(url)
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
        res = await client.get(validated_url, timeout=12)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail="Failed to fetch manifest")

        base_url = str(request.base_url).rstrip("/")
        lines = res.text.split("\n")
        rewritten_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("http"):
                encoded = urllib.parse.quote_plus(stripped)
                if ".ts" in stripped or "seg.ts" in stripped:
                    rewritten_lines.append(f"{base_url}/api/v1/proxy/ts?url={encoded}")
                elif ".m3u8" in stripped:
                    rewritten_lines.append(f"{base_url}/api/v1/proxy/m3u8?url={encoded}")
                else:
                    rewritten_lines.append(f"{base_url}/api/v1/proxy/ts?url={encoded}")
            elif stripped and not stripped.startswith("#"):
                rewritten_lines.append(stripped)
            else:
                rewritten_lines.append(line)

        return Response(content="\n".join(rewritten_lines), media_type="application/vnd.apple.mpegurl")


@app.get("/api/v1/proxy/ts")
async def proxy_ts(url: str, user=Depends(verify_viewer)):
    validated_url = validate_proxy_url(url)
    async def stream_ts():
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
            async with client.stream("GET", validated_url, timeout=18) as r:
                async for chunk in r.aiter_bytes(chunk_size=32768):
                    yield chunk

    return StreamingResponse(stream_ts(), media_type="video/mp2t")


# ---------------------------------------------------------------------------
# Real-Time Telemetry API
# ---------------------------------------------------------------------------

from .workers.ai_worker import latest_telemetry


@app.get("/api/v1/camera-telemetry")
def get_cameras_telemetry(user=Depends(verify_viewer)):
    return latest_telemetry


@app.get("/api/v1/analytics/heatmap")
def get_spatial_heatmap_data(camera_id: str = Query(default="cam_1"), user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """
    Returns spatial density heatmap grid points based on active/historical object tracks for live overlay.
    """
    import random
    # Query recent tracks for the camera
    recent_tracks = db.query(Track).filter(Track.camera_id == camera_id).limit(40).all()
    points = []
    
    if recent_tracks:
        for t in recent_tracks:
            # Map tracks to normalized 0-1 x, y center coordinates with intensity weight
            px = getattr(t, 'bbox_x', 0.5)
            py = getattr(t, 'bbox_y', 0.5)
            points.append({
                "x": round(px if px <= 1.0 else px / 1920.0, 3),
                "y": round(py if py <= 1.0 else py / 1080.0, 3),
                "value": round(getattr(t, 'speed', 10.0) / 100.0 if getattr(t, 'speed', 10.0) > 0 else 0.5, 2)
            })
    else:
        cfg = get_models()
        if cfg.get("demo_mode", False):
            # High density hotspot clusters for live demonstration
            hotspots = [
                (0.35, 0.45, 0.9), (0.38, 0.48, 0.85), (0.70, 0.60, 0.95),
                (0.20, 0.30, 0.7), (0.50, 0.50, 0.8), (0.75, 0.65, 0.88),
                (0.85, 0.70, 0.75), (0.15, 0.80, 0.6), (0.40, 0.40, 0.92)
            ]
            for x, y, v in hotspots:
                points.append({"x": x, "y": y, "value": v})
            
    return {
        "camera_id": camera_id,
        "grid_resolution": "high",
        "points_count": len(points),
        "heatmap_points": points
    }


# ---------------------------------------------------------------------------
# PTZ & Target Auto-Tracking API
# ---------------------------------------------------------------------------

from .services.onvif_ptz import send_ptz_command
from .services.ptz_tracker import toggle_auto_tracking, is_auto_tracking_active


@app.post("/api/v1/cameras/{camera_id}/ptz/control")
async def control_ptz(camera_id: str, payload: dict, user=Depends(verify_operator), db: Session = Depends(get_db)):
    """
    Dispatches manual ONVIF PTZ commands (Pan/Tilt/Zoom, Stop) to target IP camera.
    """
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    action = payload.get("action", "ContinuousMove")
    pan = float(payload.get("pan", 0.0))
    tilt = float(payload.get("tilt", 0.0))
    zoom = float(payload.get("zoom", 0.0))

    # Extract IP address from camera stream URL if applicable
    import urllib.parse
    parsed = urllib.parse.urlparse(cam.stream_url if cam.stream_url.startswith("http") or cam.stream_url.startswith("rtsp") else "http://127.0.0.1")
    ip = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80

    res = await send_ptz_command(ip, port, action, pan, tilt, zoom)
    return {"camera_id": camera_id, "ptz_result": res}


@app.post("/api/v1/cameras/{camera_id}/ptz/auto-track")
def set_ptz_auto_track(camera_id: str, payload: dict, user=Depends(verify_operator)):
    """
    Toggles automatic PTZ target tracking on a camera stream.
    """
    enabled = payload.get("enabled", False)
    target_id = payload.get("target_id", None)
    res = toggle_auto_tracking(camera_id, enabled, target_id)
    return res


# ---------------------------------------------------------------------------
# Traffic Analytics & Speed Estimation API
# ---------------------------------------------------------------------------

from .services.traffic_analytics import compute_traffic_analytics


@app.get("/api/v1/analytics/traffic-speed")
def get_traffic_speed_analytics(camera_id: str = Query(default="cam_1"), user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """
    Returns live vehicle count, speed distribution (km/h), max speed, and wrong-direction violations.
    """
    recent_tracks = db.query(Track).filter(Track.camera_id == camera_id).limit(50).all()
    tracks_payload = []
    for tr in recent_tracks:
        tracks_payload.append({
            "track_uuid": tr.track_uuid,
            "label": tr.label,
            "speed": tr.speed,
            "path_history": json.loads(tr.path_history) if tr.path_history else []
        })

    analytics = compute_traffic_analytics(tracks_payload)
    return {"camera_id": camera_id, "traffic_analytics": analytics}


# ---------------------------------------------------------------------------
# Natural Language Video Question Answering (Video QA) API
# ---------------------------------------------------------------------------

from .services.video_qa import answer_video_question


@app.get("/api/v1/forensics/video-qa")
def natural_language_video_qa(question: str = Query(...), camera_id: str = Query(default=None), user=Depends(verify_viewer)):
    """
    Conversational VLM video question answering across indexed video frame captions and metadata.
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question parameter is required.")

    res = answer_video_question(question, camera_id=camera_id)
    return res


# ---------------------------------------------------------------------------
# Captured Records Ledger API (Faces, Vehicles, License Plates, Scene Captions)
# ---------------------------------------------------------------------------

@app.get("/api/v1/records/stats")
def get_records_stats(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    """Summary counts for all captured faces, vehicles, number plates, and scene captions."""
    faces_count = db.query(Face).count()
    vehicles_count = db.query(Vehicle).count()
    plates_count = db.query(Vehicle).filter(Vehicle.license_plate.isnot(None)).count()
    captions_count = db.query(SceneCaption).count()
    identities_count = db.query(GlobalIdentity).count()
    return {
        "faces_count": faces_count,
        "vehicles_count": vehicles_count,
        "plates_count": plates_count,
        "captions_count": captions_count,
        "identities_count": identities_count
    }


@app.get("/api/v1/records/faces")
def get_records_faces(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Retrieve captured faces log with snapshot and identity details."""
    q = db.query(Face)
    if search:
        q = q.filter(Face.label.ilike(f"%{search}%") | Face.track_uuid.ilike(f"%{search}%"))
    total = q.count()
    order_clause = Face.id.desc() if sort.lower() == "desc" else Face.id.asc()
    items = q.order_by(order_clause).offset(offset).limit(limit).all()
    results = []
    for f in items:
        results.append({
            "id": f.id,
            "track_uuid": f.track_uuid,
            "label": f.label or "Unidentified Subject",
            "confidence": round(f.confidence, 2) if f.confidence else 0.85,
            "timestamp": f.timestamp.strftime("%Y-%m-%d %H:%M:%S") if f.timestamp else None,
            "snapshot_url": f"/api/v1/playback/snapshot/{f.embedding_id}" if f.embedding_id else None
        })
    return {"total": total, "items": results}


@app.get("/api/v1/records/vehicles")
def get_records_vehicles(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    camera_id: str = Query(default=None),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Retrieve captured vehicles log with color, type, track, and camera source."""
    q = db.query(Vehicle)
    if camera_id:
        q = q.filter(Vehicle.camera_id == camera_id)
    if search:
        q = q.filter(
            (Vehicle.vehicle_type.ilike(f"%{search}%")) |
            (Vehicle.vehicle_color.ilike(f"%{search}%")) |
            (Vehicle.license_plate.ilike(f"%{search}%")) |
            (Vehicle.track_uuid.ilike(f"%{search}%"))
        )
    total = q.count()
    order_clause = Vehicle.id.desc() if sort.lower() == "desc" else Vehicle.id.asc()
    items = q.order_by(order_clause).offset(offset).limit(limit).all()
    results = []
    for v in items:
        results.append({
            "id": v.id,
            "camera_id": v.camera_id,
            "track_uuid": v.track_uuid,
            "license_plate": v.license_plate,
            "vehicle_type": v.vehicle_type or "car",
            "vehicle_color": v.vehicle_color or "unknown",
            "ocr_confidence": round(v.ocr_confidence, 2) if v.ocr_confidence else 0.0,
            "timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else None
        })
    return {"total": total, "items": results}


@app.get("/api/v1/records/plates")
def get_records_plates(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Retrieve captured license plate OCR log."""
    q = db.query(Vehicle).filter(Vehicle.license_plate.isnot(None))
    if search:
        q = q.filter(Vehicle.license_plate.ilike(f"%{search}%"))
    total = q.count()
    order_clause = Vehicle.id.desc() if sort.lower() == "desc" else Vehicle.id.asc()
    items = q.order_by(order_clause).offset(offset).limit(limit).all()
    results = []
    for v in items:
        results.append({
            "id": v.id,
            "camera_id": v.camera_id,
            "track_uuid": v.track_uuid,
            "license_plate": v.license_plate,
            "vehicle_type": v.vehicle_type,
            "ocr_confidence": round(v.ocr_confidence, 2) if v.ocr_confidence else 0.90,
            "timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else None
        })
    return {"total": total, "items": results}


@app.get("/api/v1/records/captions")
def get_records_captions(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    camera_id: str = Query(default=None),
    search: str = Query(default=None),
    sort: str = Query(default="desc"),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Retrieve all generated AI scene captions log across cameras."""
    q = db.query(SceneCaption)
    if camera_id:
        q = q.filter(SceneCaption.camera_id == camera_id)
    if search:
        q = q.filter(SceneCaption.caption.ilike(f"%{search}%"))
    total = q.count()
    order_clause = SceneCaption.id.desc() if sort.lower() == "desc" else SceneCaption.id.asc()
    items = q.order_by(order_clause).offset(offset).limit(limit).all()
    results = []
    for c in items:
        results.append({
            "id": c.id,
            "camera_id": c.camera_id,
            "caption": c.caption,
            "snapshot_url": c.snapshot_url,
            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S") if c.timestamp else None
        })
    return {"total": total, "items": results}



