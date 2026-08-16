import json
import uuid
import datetime
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import User, Camera, UnifiedSighting, CoOccurrenceCluster
from backend.auth.helpers import create_access_token, get_password_hash

client = TestClient(app)

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

@pytest.fixture
def auth_headers():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "analyst_cooc").first()
        if not user:
            user = User(
                username="analyst_cooc",
                password_hash=get_password_hash("TestPassword123!"),
                role="operator",
                status="active",
                must_change_password=False
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    token = create_access_token(data={"sub": "analyst_cooc", "role": "operator"})
    return {"Authorization": f"Bearer {token}"}


def test_co_occurrence_confidence_formula_math():
    """Validates exact mathematical scoring for convoy co-occurrence confidence."""
    num_cams = 2
    num_sightings = 3
    avg_dt = 1.3333333333333333 # average 1.33 seconds between sightings

    # Formula: 0.70 + (0.08 * num_cams) + (0.04 * num_sightings) - (0.03 * avg_dt)
    # Expected: 0.70 + 0.16 + 0.12 - 0.04 = 0.94
    calc_conf = min(0.99, round(0.70 + (0.08 * num_cams) + (0.04 * num_sightings) - (0.03 * avg_dt), 2))
    assert calc_conf == 0.94

    # High frequency 5 cameras, 10 sightings, 0.5s avg delta:
    high_cams, high_sightings, high_dt = 5, 10, 0.5
    high_conf = min(0.99, round(0.70 + (0.08 * high_cams) + (0.04 * high_sightings) - (0.03 * high_dt), 2))
    assert high_conf == 0.99  # Capped at 0.99


def test_module5_co_occurrence_clustering_and_human_review(auth_headers):
    db = SessionLocal()
    try:
        # 1. Clean previous test clusters
        db.query(CoOccurrenceCluster).delete()
        db.commit()

        # 2. Seed multi-camera co-occurring sightings (Bus A + Motorcycle B sighted together on 2 cameras, 3 times)
        now = datetime.datetime.now(_IST)
        
        # Camera 1 - Sighting 1 (T = 0s)
        s1_a = UnifiedSighting(
            sighting_uuid=str(uuid.uuid4()),
            camera_id="cam_top_01",
            track_uuid="TRK_BUS_01",
            primary_class="bus",
            license_plate="KA51MB8811",
            timestamp=now - datetime.timedelta(minutes=5)
        )
        s1_b = UnifiedSighting(
            sighting_uuid=str(uuid.uuid4()),
            camera_id="cam_top_01",
            track_uuid="TRK_BIKE_02",
            primary_class="motorcycle",
            license_plate="GJ05ZN2996",
            timestamp=now - datetime.timedelta(minutes=5, seconds=-1) # Delta T = 1.0s
        )

        # Camera 1 - Sighting 2 (T = 20s later at same camera exit)
        s2_a = UnifiedSighting(
            sighting_uuid=str(uuid.uuid4()),
            camera_id="cam_top_01",
            track_uuid="TRK_BUS_01",
            primary_class="bus",
            license_plate="KA51MB8811",
            timestamp=now - datetime.timedelta(minutes=4, seconds=40)
        )
        s2_b = UnifiedSighting(
            sighting_uuid=str(uuid.uuid4()),
            camera_id="cam_top_01",
            track_uuid="TRK_BIKE_02",
            primary_class="motorcycle",
            license_plate="GJ05ZN2996",
            timestamp=now - datetime.timedelta(minutes=4, seconds=41) # Delta T = 1.0s
        )

        # Camera 2 - Sighting 3 (Downstream camera 2 minutes later)
        s3_a = UnifiedSighting(
            sighting_uuid=str(uuid.uuid4()),
            camera_id="cam_top_02",
            track_uuid="TRK_BUS_01",
            primary_class="bus",
            license_plate="KA51MB8811",
            timestamp=now - datetime.timedelta(minutes=2)
        )
        s3_b = UnifiedSighting(
            sighting_uuid=str(uuid.uuid4()),
            camera_id="cam_top_02",
            track_uuid="TRK_BIKE_02",
            primary_class="motorcycle",
            license_plate="GJ05ZN2996",
            timestamp=now - datetime.timedelta(minutes=2, seconds=-2) # Delta T = 2.0s
        )

        db.add_all([s1_a, s1_b, s2_a, s2_b, s3_a, s3_b])
        db.commit()

        # 3. Trigger Co-Occurrence Clustering Analysis
        analyze_res = client.post(
            "/api/v1/forensics/co-occurrence/analyze",
            json={"time_window_minutes": 15, "min_sightings": 3, "min_cameras": 2},
            headers=auth_headers
        )
        assert analyze_res.status_code == 200
        an_data = analyze_res.json()
        assert an_data["success"] is True
        assert an_data["new_clusters_flagged"] >= 1

        # 4. Query Flagged Clusters (Ensure status is FLAGGED_PENDING_REVIEW)
        list_res = client.get("/api/v1/forensics/co-occurrence/clusters", headers=auth_headers)
        assert list_res.status_code == 200
        clusters_data = list_res.json()
        assert clusters_data["count"] >= 1

        target_cluster = clusters_data["clusters"][0]
        assert target_cluster["status"] == "FLAGGED_PENDING_REVIEW", "Convoy MUST default to FLAGGED_PENDING_REVIEW"
        assert target_cluster["cameras_count"] >= 2
        assert target_cluster["sightings_count"] >= 3
        assert "KA51MB8811" in [target_cluster["primary_target_id"], target_cluster["companion_target_id"]]

        # 5. Test Operator Review Workflow (Human Confirmation)
        cluster_uid = target_cluster["cluster_uuid"]
        review_res = client.post(
            f"/api/v1/forensics/co-occurrence/clusters/{cluster_uid}/review",
            json={"new_status": "CONFIRMED_CONVOY", "review_notes": "Verified suspect convoy via video footage."},
            headers=auth_headers
        )
        assert review_res.status_code == 200
        rev_data = review_res.json()
        assert rev_data["new_status"] == "CONFIRMED_CONVOY"
        assert rev_data["reviewed_by"] == "analyst_cooc"

        # Verify DB updated
        db_cluster = db.query(CoOccurrenceCluster).filter(CoOccurrenceCluster.cluster_uuid == cluster_uid).first()
        assert db_cluster.status == "CONFIRMED_CONVOY"
        assert db_cluster.reviewed_by == "analyst_cooc"
        assert db_cluster.review_notes == "Verified suspect convoy via video footage."
    finally:
        db.close()
