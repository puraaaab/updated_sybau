import os
import json
import threading

CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "configs"))

_CONFIG_CACHE = {}
_CONFIG_CACHE_LOCK = threading.Lock()


def _get_config_path(filename):
    return os.path.join(CONFIG_DIR, filename)


def _invalidate_config_cache(filename=None):
    with _CONFIG_CACHE_LOCK:
        if filename is None:
            _CONFIG_CACHE.clear()
        else:
            _CONFIG_CACHE.pop(filename, None)

def _read_json(filename, default=None):
    filepath = _get_config_path(filename)
    if not os.path.exists(filepath):
        return default or {}

    file_mtime = os.path.getmtime(filepath)
    with _CONFIG_CACHE_LOCK:
        cached = _CONFIG_CACHE.get(filename)
        if cached and cached[0] == file_mtime:
            return cached[1]

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        with _CONFIG_CACHE_LOCK:
            _CONFIG_CACHE[filename] = (file_mtime, data)
        return data
    except Exception as e:
        print(f"Error reading config {filename}: {e}")
        return default or {}

def _write_json(filename, data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    filepath = _get_config_path(filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        _invalidate_config_cache(filename)
        return True
    except Exception as e:
        print(f"Error writing config {filename}: {e}")
        return False

def get_cameras():
    try:
        from ..database.connection import SessionLocal
        from ..database.models import Camera
        with SessionLocal() as db:
            cams = db.query(Camera).all()
            if cams is not None and len(cams) > 0:
                return [
                    {
                        "id": c.id,
                        "name": c.name,
                        "stream_url": c.stream_url,
                        "status": c.status,
                        "width": c.width,
                        "height": c.height,
                        "location": c.location or "Unknown",
                        "latitude": getattr(c, "latitude", 21.1702),
                        "longitude": getattr(c, "longitude", 72.8311),
                    }
                    for c in cams
                ]
    except Exception:
        pass
    return _read_json("cameras.json", default=[])

def save_cameras(cameras_data):
    return _write_json("cameras.json", cameras_data)

def get_zones():
    return _read_json("zones.json", default={})

def save_zones(zones_data):
    return _write_json("zones.json", zones_data)

def get_alerts():
    return _read_json("alerts.json", default={})

def save_alerts(alerts_data):
    return _write_json("alerts.json", alerts_data)

def get_models():
    return _read_json("models.json", default={})

def save_models(models_data):
    return _write_json("models.json", models_data)

def get_privacy_settings():
    return _read_json("privacy.json", default={
        "enabled": False,
        "redact_faces": True,
        "redact_plates": True,
        "blur_kernel_size": 51
    })

def save_privacy_settings(privacy_data):
    return _write_json("privacy.json", privacy_data)

