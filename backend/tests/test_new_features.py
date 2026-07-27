import pytest
pytest.importorskip("bcrypt")
pytest.importorskip("sqlalchemy")
from backend.auth.helpers import verify_camera_access, User
from backend.services.onvif_ptz import build_ptz_soap_envelope
from backend.services.ptz_tracker import compute_ptz_error_velocities, toggle_auto_tracking, is_auto_tracking_active
from backend.services.traffic_analytics import calculate_speed_kmh, check_directional_compliance, compute_traffic_analytics
from backend.services.video_qa import answer_video_question

def test_granular_camera_permissions():
    admin = User(username="admin_user", role="admin", allowed_cameras="[]")
    assert verify_camera_access("cam_1", admin) is True

    op_restricted = User(username="op_restricted", role="operator", allowed_cameras='["cam_1", "cam_2"]')
    assert verify_camera_access("cam_1", op_restricted) is True
    assert verify_camera_access("cam_3", op_restricted) is False

    op_unrestricted = User(username="op_all", role="operator", allowed_cameras="[]")
    assert verify_camera_access("cam_3", op_unrestricted) is True

def test_onvif_ptz_envelope():
    xml_move = build_ptz_soap_envelope("ContinuousMove", pan=0.5, tilt=-0.2, zoom=0.0)
    assert "ContinuousMove" in xml_move
    assert 'x="0.50"' in xml_move

    xml_stop = build_ptz_soap_envelope("Stop")
    assert "Stop" in xml_stop

def test_ptz_auto_tracker():
    res = toggle_auto_tracking("cam_1", True, "target_101")
    assert res["auto_tracking"] is True
    assert is_auto_tracking_active("cam_1") is True

    pan_v, tilt_v = compute_ptz_error_velocities((1000, 500, 1100, 600), 1920, 1080)
    assert isinstance(pan_v, float)
    assert isinstance(tilt_v, float)

def test_speed_and_traffic_analytics():
    # 300px displacement over 1 second with 15 px/meter scale = 20 m/s = 72 km/h
    speed = calculate_speed_kmh((0, 0), (300, 0), 1.0, 15.0)
    assert speed == 72.0

    # Directional compliance: same vector direction should pass
    assert check_directional_compliance((10, 0), (1, 0)) is True
    # Opposite direction vector should fail (wrong way)
    assert check_directional_compliance((-10, 0), (1, 0)) is False

    analytics = compute_traffic_analytics([
        {"track_uuid": "t1", "label": "car", "speed": 15.0, "path_history": [[0,0], [10,0]]},
        {"track_uuid": "t2", "label": "car", "speed": 25.0, "path_history": [[10,0], [0,0]]}
    ], direction_vector=(1.0, 0.0))

    assert analytics["total_vehicles_count"] == 2
    assert analytics["wrong_direction_violations"] == 1

def test_natural_language_video_qa():
    ans = answer_video_question("Is there a red car near the gate?", camera_id="cam_1")
    assert "question" in ans
    assert "answer" in ans
    assert "evidence" in ans
