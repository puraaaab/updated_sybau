"""
Unit tests for Predictive Next-Hop Escape Routing (Prompt 1.3)
and Convoy / Shadow-Vehicle Co-Occurrence Detection (Prompt 6.1).
"""

import datetime
import pytest
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal, engine
from backend.database.models import Base, Camera, CameraEdge, CameraNode, VehicleJourneyEvent
from backend.services.topology.escape_router import predict_next_hop_escape_routes
from backend.services.co_occurrence import find_convoy_companions, seed_demo_convoy_data


@pytest.fixture(autouse=True)
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            from backend.database.models import Camera, CameraEdge, VehicleJourneyEvent
            db.query(CameraEdge).filter(
                (CameraEdge.source_camera_id.like("cam_route%")) | (CameraEdge.target_camera_id.like("cam_route%"))
            ).delete(synchronize_session=False)
            db.query(Camera).filter(
                (Camera.id.like("cam_route%")) | (Camera.id == "cam_dead_end")
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def test_predictive_next_hop_escape_routing(db_session: Session):
    # Ensure test cameras exist
    c1 = db_session.query(Camera).filter_by(id="cam_route_1").first()
    if not c1:
        c1 = Camera(id="cam_route_1", name="Sector 4 Main Road", location="Sector 4 Junction", stream_url="rtsp://127.0.0.1:8554/cam_route_1", latitude=28.61, longitude=77.20)
        db_session.add(c1)

    c2 = db_session.query(Camera).filter_by(id="cam_route_2").first()
    if not c2:
        c2 = Camera(id="cam_route_2", name="Sector 5 North Toll", location="North Expressway Toll", stream_url="rtsp://127.0.0.1:8554/cam_route_2", latitude=28.63, longitude=77.20)
        db_session.add(c2)

    c3 = db_session.query(Camera).filter_by(id="cam_route_3").first()
    if not c3:
        c3 = Camera(id="cam_route_3", name="Sector 3 South Exit", location="South Flyover", stream_url="rtsp://127.0.0.1:8554/cam_route_3", latitude=28.59, longitude=77.20)
        db_session.add(c3)

    db_session.commit()

    # Create explicit directed edges
    e1 = db_session.query(CameraEdge).filter_by(source_camera_id="cam_route_1", target_camera_id="cam_route_2").first()
    if not e1:
        e1 = CameraEdge(
            source_camera_id="cam_route_1",
            target_camera_id="cam_route_2",
            distance_meters=800.0,
            expected_transit_sec_min=60,
            expected_transit_sec_max=150,
            allowed_directions='["north", "forward"]',
            is_active=True,
        )
        db_session.add(e1)

    e2 = db_session.query(CameraEdge).filter_by(source_camera_id="cam_route_1", target_camera_id="cam_route_3").first()
    if not e2:
        e2 = CameraEdge(
            source_camera_id="cam_route_1",
            target_camera_id="cam_route_3",
            distance_meters=1200.0,
            expected_transit_sec_min=90,
            expected_transit_sec_max=240,
            allowed_directions='["south"]',
            is_active=True,
        )
        db_session.add(e2)

    db_session.commit()

    dep_time = datetime.datetime(2026, 8, 15, 14, 15, 0)
    result = predict_next_hop_escape_routes(
        db=db_session,
        source_camera_identifier="cam_route_1",
        target_description="Red Sedan",
        heading_direction="north",
        departure_time=dep_time,
        observed_speed_kmh=40.0,
    )

    assert result["success"] is True
    assert result["predicted_next_hops_count"] >= 1
    top_route = result["routes"][0]
    # Northern camera should rank top priority
    assert "North" in top_route["camera_name"] or top_route["camera_id"] == "cam_route_2"
    assert top_route["intercept_probability"] >= 0.80
    assert top_route["eta_window_start"] > "14:15:00"


def test_convoy_detection_across_multiple_cameras(db_session: Session):
    # Seed multi-camera convoy sightings
    seed_result = seed_demo_convoy_data(db_session)
    assert seed_result["success"] is True
    assert seed_result["target"] == "DL01AB1234"
    assert seed_result["companion"] == "HR26DK9901"

    # Query convoy for target
    convoy_report = find_convoy_companions(
        db=db_session,
        target_identifier="DL01AB1234",
        time_window_minutes=60,
        max_gap_seconds=45.0,
        min_cameras=2,
    )

    assert convoy_report["success"] is True
    assert convoy_report["convoys_detected_count"] >= 1
    companion = convoy_report["convoy_candidates"][0]
    assert companion["companion_identifier"] == "HR26DK9901"
    assert companion["cameras_co_occurred_count"] >= 2
    assert companion["avg_trailing_gap_seconds"] <= 15.0
    assert companion["correlation_confidence"] >= 0.80
    assert companion["threat_assessment"] == "SUSPECTED_SHADOW_ESCORT"


def test_single_camera_co_occurrence_not_flagged_as_multi_cam_convoy(db_session: Session):
    # If two vehicles only cross 1 camera together, they shouldn't trigger a multi-camera convoy alert
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    isolated_target = "TEST_TGT_999"
    isolated_random = "TEST_RND_888"

    db_session.query(VehicleJourneyEvent).filter(
        VehicleJourneyEvent.license_plate.in_([isolated_target, isolated_random])
    ).delete(synchronize_session=False)

    db_session.add(VehicleJourneyEvent(
        global_vehicle_id="VEH_ISO_1",
        track_id="trk_iso_1",
        camera_id="cam_route_1",
        license_plate=isolated_target,
        timestamp_start=now - datetime.timedelta(minutes=5),
        timestamp_end=now - datetime.timedelta(minutes=5),
    ))
    db_session.add(VehicleJourneyEvent(
        global_vehicle_id="VEH_ISO_2",
        track_id="trk_iso_2",
        camera_id="cam_route_1",
        license_plate=isolated_random,
        timestamp_start=now - datetime.timedelta(minutes=5, seconds=-10),
        timestamp_end=now - datetime.timedelta(minutes=5, seconds=-6),
    ))
    db_session.commit()

    report = find_convoy_companions(
        db=db_session,
        target_identifier=isolated_target,
        time_window_minutes=60,
        max_gap_seconds=45.0,
        min_cameras=2,  # Require at least 2 distinct checkpoints
    )

    # Should find 0 convoy candidates because they only co-occurred at 1 camera
    assert report["convoys_detected_count"] == 0


def test_dead_end_terminal_camera_negative_case(db_session: Session):
    # Create a camera with 0 outgoing edges (dead end)
    c_dead = db_session.query(Camera).filter_by(id="cam_dead_end").first()
    if not c_dead:
        c_dead = Camera(
            id="cam_dead_end",
            name="Cul-de-Sac Terminal",
            location="Dead-End Industrial Alley",
            stream_url="rtsp://127.0.0.1:8554/dead_end",
            latitude=28.70,
            longitude=77.30,
        )
        db_session.add(c_dead)
        db_session.commit()

    # Ensure other edges exist in the network
    assert db_session.query(CameraEdge).count() > 0

    result = predict_next_hop_escape_routes(
        db=db_session,
        source_camera_identifier="cam_dead_end",
        target_description="Suspect Vehicle",
        heading_direction="north",
    )

    assert result["success"] is True
    assert result.get("is_dead_end") is True
    assert result["predicted_next_hops_count"] == 0
    assert len(result["routes"]) == 0
    assert "terminal boundary checkpoint" in result["message"]


def test_non_existent_target_convoy_negative_case(db_session: Session):
    # Query for a non-existent vehicle plate
    report = find_convoy_companions(
        db=db_session,
        target_identifier="NON_EXISTENT_999",
        time_window_minutes=60,
        max_gap_seconds=45.0,
        min_cameras=2,
    )

    assert report["success"] is False
    assert report["convoys_detected_count"] == 0
    assert len(report["convoy_candidates"]) == 0
    assert "No sightings found" in report["message"]


def test_copilot_escape_routing_phrasing_variations(db_session: Session):
    from backend.services.copilot.chat_engine import chat_engine
    from backend.database.models import Camera, CameraEdge

    c1 = db_session.query(Camera).filter_by(id="cam_route_1").first()
    if not c1:
        db_session.add(Camera(id="cam_route_1", name="Sector 4 Main Road", location="Sector 4 Junction", stream_url="rtsp://127.0.0.1:8554/cam_route_1", latitude=28.61, longitude=77.20))
        db_session.add(Camera(id="cam_route_2", name="Sector 5 North Toll", location="North Expressway Toll", stream_url="rtsp://127.0.0.1:8554/cam_route_2", latitude=28.63, longitude=77.20))
        db_session.add(CameraEdge(source_camera_id="cam_route_1", target_camera_id="cam_route_2", distance_meters=800.0, expected_transit_sec_min=60, expected_transit_sec_max=150, allowed_directions='["north", "forward"]', is_active=True))
        db_session.commit()

    variations = [
        "Where is this red car likely heading next from Sector 4 Main Road?",
        "Next camera for suspect vehicle going north from Sector 4",
        "Predict escape path if suspect left Sector 4 at 10:30am",
        "Which cameras should I monitor next from Sector 4 Main Road?",
    ]

    for q in variations:
        resp = chat_engine.process_text_query(user_query=q)
        assert resp is not None
        assert "text" in resp
        # Confirm it dispatched to predictive routing and gave a structured answer
        assert "Predictive Next-Hop Escape Routing Analysis" in resp["text"] or "Downstream Interception Cameras" in resp["text"]
        assert len(resp.get("timeline", [])) >= 1

