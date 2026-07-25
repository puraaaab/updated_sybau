import os
import json

CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "configs"))

def _read_json(filename, default=None):
    filepath = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(filepath):
        return default or {}
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading config {filename}: {e}")
        return default or {}

def _write_json(filename, data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    filepath = os.path.join(CONFIG_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error writing config {filename}: {e}")
        return False

def get_cameras():
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
