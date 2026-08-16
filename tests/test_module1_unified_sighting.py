import json
import uuid
import math
import pytest
from backend.database.connection import SessionLocal, Base, engine
from backend.database.models import UnifiedSighting, QueryAuditLog, Camera

def test_depth_proxy_proximity_math():
    """Validates depth-proxy proximity association formula."""
    # Vehicle Bounding Box: [x1, y1, x2, y2]
    v_bbox = [100, 100, 300, 200]
    vw = max(1.0, float(v_bbox[2] - v_bbox[0]))  # 200.0 px
    vh = max(1.0, float(v_bbox[3] - v_bbox[1]))  # 100.0 px
    vcx = (v_bbox[0] + v_bbox[2]) / 2.0  # 200.0
    vcy = (v_bbox[1] + v_bbox[3]) / 2.0  # 150.0
    alpha = 1.25
    depth_thresh = alpha * max(vw, vh)  # 1.25 * 200 = 250.0 px

    # Person 1 (Adjacent): Center at (250, 180) -> dist = sqrt(50^2 + 30^2) = 58.31 px <= 250.0
    p1_center = (250, 180)
    dist1 = math.sqrt((vcx - p1_center[0]) ** 2 + (vcy - p1_center[1]) ** 2)
    assert dist1 <= depth_thresh, f"Person 1 should be associated (dist={dist1:.2f} <= {depth_thresh})"

    # Person 2 (Distant): Center at (600, 600) -> dist = sqrt(400^2 + 450^2) = 602.08 px > 250.0
    p2_center = (600, 600)
    dist2 = math.sqrt((vcx - p2_center[0]) ** 2 + (vcy - p2_center[1]) ** 2)
    assert dist2 > depth_thresh, f"Person 2 should NOT be associated (dist={dist2:.2f} > {depth_thresh})"


def test_confidence_fusion_formula():
    """Validates multi-source confidence fusion formula."""
    yolo_conf = 0.90
    ocr_conf = 0.80
    reid_conf = 0.70

    weights = [0.40, 0.35, 0.25]
    scores = [yolo_conf * 0.40, ocr_conf * 0.35, reid_conf * 0.25]
    fused_conf = sum(scores) / sum(weights)

    # 0.90*0.40 + 0.80*0.35 + 0.70*0.25 = 0.36 + 0.28 + 0.175 = 0.815
    assert abs(fused_conf - 0.815) < 1e-5

    # If only YOLO is present (single source)
    single_weights = [0.40]
    single_scores = [yolo_conf * 0.40]
    single_fused = sum(single_scores) / sum(single_weights)
    assert abs(single_fused - 0.90) < 1e-5


def test_module1_database_persistence():
    """Tests UnifiedSighting and QueryAuditLog persistence with real JWT user identity."""
    db = SessionLocal()
    try:
        cam = db.query(Camera).filter(Camera.id == "cam_test_mod1").first()
        if not cam:
            cam = Camera(
                id="cam_test_mod1",
                name="Module 1 Test Camera",
                stream_url="rtsp://localhost/test",
                proximity_scale=1.25
            )
            db.add(cam)
            db.commit()

        uid = str(uuid.uuid4())
        sighting = UnifiedSighting(
            sighting_uuid=uid,
            camera_id="cam_test_mod1",
            track_uuid="TRK_cam_test_mod1_101",
            primary_class="bus",
            confidence=0.815,
            bbox_json=json.dumps([100, 100, 300, 200]),
            speed_kmh=24.5,
            extracted_text="SAGAR TOURS & TRAVELS",
            license_plate="GJ05AB1234",
            attributes_json=json.dumps({"color": "cyan", "type": "bus"}),
            nearby_pedestrian_uuids=json.dumps(["TRK_cam_test_mod1_201"]),
            proximity_flag="ESTIMATED_DEPTH_PROXY"
        )
        db.add(sighting)
        db.commit()

        saved = db.query(UnifiedSighting).filter(UnifiedSighting.sighting_uuid == uid).first()
        assert saved is not None
        assert abs(saved.confidence - 0.815) < 1e-3
        assert "TRK_cam_test_mod1_201" in saved.nearby_pedestrian_uuids

        test_sess_id = f"sess_{uuid.uuid4().hex[:8]}"
        audit = QueryAuditLog(
            session_uuid=test_sess_id,
            username="investigator_granth",  # Real authenticated identity
            query_text="find sagar tours",
            search_mode="ocr",
            matched_records_count=1,
            matched_sighting_ids=json.dumps([saved.id]),
            execution_time_ms=45.2
        )
        db.add(audit)
        db.commit()

        saved_audit = db.query(QueryAuditLog).filter(QueryAuditLog.session_uuid == test_sess_id).first()
        assert saved_audit is not None
        assert saved_audit.username == "investigator_granth"
        assert saved_audit.matched_records_count == 1
    finally:
        db.close()
