import numpy as np
import pytest
from concurrent.futures import ThreadPoolExecutor

from backend.ai.vehicle.vehicle_reid import (
    detect_vehicle_color,
    detect_vehicle_color_fallback,
    detect_vehicle_color_clip
)
from backend.workers.ai_worker import (
    set_latest_telemetry,
    get_latest_telemetry,
    remove_latest_telemetry,
    save_snapshot_async,
    _on_snapshot_saved
)

def test_color_method_labeling_and_fallback(monkeypatch):
    # Test crop: 50x50 BGR image
    crop = np.full((50, 50, 3), 128, dtype=np.uint8)

    # 1. Force HSV fallback path via config
    monkeypatch.setattr(
        "backend.ai.vehicle.vehicle_reid.get_models",
        lambda: {"vehicle": {"use_hsv_fallback_only": True}}
    )
    color, method = detect_vehicle_color(crop)
    assert method == "hsv_fallback"
    assert isinstance(color, str)

    # 2. Dynamic CLIP path (or automatic fallback if CLIP unavailable in demo/test env)
    monkeypatch.setattr(
        "backend.ai.vehicle.vehicle_reid.get_models",
        lambda: {"vehicle": {"use_hsv_fallback_only": False}, "demo_mode": True}
    )
    color2, method2 = detect_vehicle_color(crop)
    assert method2 in ("clip", "hsv_fallback")
    assert isinstance(color2, str)

def test_telemetry_thread_safety():
    test_cam = "cam_test_lock"
    telemetry_data = {"tracks": [], "fps": 5.0, "status": "OK"}

    set_latest_telemetry(test_cam, telemetry_data)
    retrieved = get_latest_telemetry(test_cam)
    assert retrieved == telemetry_data
    assert retrieved is not telemetry_data  # Should return a copy for thread safety

    all_telemetry = get_latest_telemetry()
    assert test_cam in all_telemetry

    remove_latest_telemetry(test_cam)
    assert get_latest_telemetry(test_cam) is None

def test_save_snapshot_async_done_callback(tmp_path):
    out_file = str(tmp_path / "test_snap.jpg")
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Should run asynchronously without error
    save_snapshot_async(out_file, frame)
