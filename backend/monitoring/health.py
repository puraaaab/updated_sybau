import os
import sys
import psutil
import datetime
from sqlalchemy import text
from ..config.service import get_cameras, get_models
from ..database.connection import SessionLocal
from ..workers.ai_worker import active_ai_workers
from ..recording.recorder import active_recorders


def _get_storage_root() -> str:
    """Return the appropriate filesystem root for disk usage on any platform."""
    if sys.platform.startswith("win"):
        # Use the drive of the current file (e.g. C:\)
        return os.path.splitdrive(os.path.abspath(__file__))[0] + "\\"
    return "/"


def get_system_vitals() -> dict:
    """
    Collects host resource utilization (CPU, RAM, Storage, and GPU stats).
    """
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()

    try:
        disk = psutil.disk_usage(_get_storage_root())
        storage_utilization = disk.percent
    except Exception:
        storage_utilization = 0.0

    # Try to read real GPU utilization via GPUtil; fall back to simulation
    gpu_stats = _get_gpu_stats()

    return {
        "cpu_utilization": cpu_percent,
        "ram_utilization": memory.percent,
        "storage_utilization": storage_utilization,
        "gpu": gpu_stats,
    }


def _get_gpu_stats() -> dict:
    """Try GPUtil for real GPU stats; return simulated values if unavailable."""
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            return {
                "name": g.name,
                "utilization": g.load * 100,
                "vram_used_mb": g.memoryUsed,
                "vram_total_mb": g.memoryTotal,
            }
    except Exception:
        pass

    # Simulation fallback (displayed when no GPU or GPUtil not installed)
    workers_active = len(active_ai_workers) > 0
    return {
        "name": "NVIDIA GeForce RTX 4060 Laptop GPU (simulated)",
        "utilization": 42.0 if workers_active else 0.0,
        "vram_used_mb": 2450.0 if workers_active else 0.0,
        "vram_total_mb": 8192.0,
    }


def get_services_health() -> dict:
    """
    Performs active health checks on PostgreSQL, Qdrant, and Kafka services.
    """
    # 1. Check PostgreSQL connection
    pg_status = "offline"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))  # SQLAlchemy 2.x requires text() wrapper
        pg_status = "online"
        db.close()
    except Exception:
        pass

    # 2. Check Qdrant status
    qd_status = "offline"
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient("http://localhost:6333", timeout=0.5)
        client.get_collections()
        qd_status = "online"
    except Exception:
        pass

    # 3. Check Kafka status
    kf_status = "offline"
    try:
        from ..messaging.kafka_client import event_client
        if event_client.connected:
            kf_status = "online"
    except Exception:
        pass

    return {
        "postgresql": pg_status,
        "qdrant": qd_status,
        "kafka": kf_status,
    }


def get_full_health_report() -> dict:
    """
    Compiles vitals, databases, camera pipelines, and worker statistics.
    """
    vitals = get_system_vitals()
    services = get_services_health()
    cameras = get_cameras()

    active_models_list = []
    cfg = get_models()
    if cfg.get("demo_mode", False):
        active_models_list = ["YOLO 26m", "YuNet+SFace", "Florence-2", "all-MiniLM-L6-v2"]
    else:
        yolo_device = cfg.get("yolo", {}).get("device", "cpu")
        active_models_list.append(f"YOLO 26m ({yolo_device.upper()})")

        if cfg.get("face", {}).get("enabled", True):
            active_models_list.append("YuNet Face Detector (CPU)")
            active_models_list.append("SFace Recognizer (CPU)")

        if cfg.get("vehicle", {}).get("enabled", True):
            ocr_engine = cfg.get("vehicle", {}).get("ocr_engine", "easyocr")
            active_models_list.append(f"EasyOCR [{ocr_engine}]")
            active_models_list.append("MobileNetV3-Small ReID (CPU)")

        if cfg.get("florence", {}).get("enabled", True):
            florence_id = cfg.get("florence", {}).get("model_id", "Florence-2-base")
            florence_device = cfg.get("florence", {}).get("device", "cpu")
            active_models_list.append(f"Florence-2 [{florence_id}] ({florence_device.upper()})")

        active_models_list.append("all-MiniLM-L6-v2 (CPU)")

    camera_health = []
    for cam in cameras:
        cid = cam["id"]
        camera_health.append({
            "id": cid,
            "name": cam["name"],
            "stream_active": cid in active_ai_workers,
            "recording_active": cid in active_recorders,
            "fps": cam.get("fps", 15),
            "status": "online" if cid in active_ai_workers else "offline",
        })

    return {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "system_vitals": vitals,
        "services": services,
        "cameras": camera_health,
        "loaded_models": active_models_list,
        "active_ai_threads": len(active_ai_workers),
        "active_recording_threads": len(active_recorders),
    }
