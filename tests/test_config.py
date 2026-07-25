import pytest
from backend.config import service as config_service

def test_cameras_config():
    cams = config_service.get_cameras()
    assert isinstance(cams, list)
    if len(cams) > 0:
        assert "id" in cams[0]
        assert "stream_url" in cams[0]

def test_alerts_config():
    alerts = config_service.get_alerts()
    assert isinstance(alerts, dict)
    assert "loitering" in alerts
    assert "crowd" in alerts
    assert "running" in alerts

def test_models_config():
    models = config_service.get_models()
    assert isinstance(models, dict)
    assert "demo_mode" in models
    assert "yolo" in models
