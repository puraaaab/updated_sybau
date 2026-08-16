import datetime
import uuid
from backend.database.connection import SessionLocal
from backend.database.models import SceneCaption, Camera, ChatSession, ChatMessage
from backend.services.copilot.chat_engine import SurveillanceChatEngine, _istnow


def test_copilot_chat_returns_snapshots_and_trajectory_for_camera_query():
    engine = SurveillanceChatEngine()
    db = SessionLocal()
    try:
        # 1. Seed cam_11 camera if not present
        cam = db.query(Camera).filter(Camera.id == "cam_11").first()
        if not cam:
            cam = Camera(
                id="cam_11",
                name="Re-ID Checkpoint 11 (IMG_0114.MOV)",
                location="Re-ID Node #11",
                stream_url="rtsp://127.0.0.1:8554/cam_11",
                latitude=21.222,
                longitude=72.842
            )
            db.add(cam)
            db.commit()

        # 2. Seed SceneCaption for cam_11 matching Sagar bus
        now = _istnow()
        snap_id = f"test_snap_{uuid.uuid4().hex[:8]}"
        sc = SceneCaption(
            camera_id="cam_11",
            caption="[Moondream]: A light blue bus, labeled 'SAGAR,' is parked on a paved road | camera cam_11",
            snapshot_url=f"/api/v1/playback/snapshot/{snap_id}",
            timestamp=now - datetime.timedelta(minutes=3)
        )
        db.add(sc)
        db.commit()

        # 3. Process natural language question containing camera ID
        session_id = f"test_chat_{uuid.uuid4().hex[:6]}"
        query = "have you ever seen this sagar tours and travels buses in cam_11"
        res = engine.process_text_query(query, session_uuid=session_id)

        # Assertions
        assert "text" in res
        assert "timeline" in res
        assert len(res["timeline"]) >= 1, "Timeline items MUST NOT be empty!"

        matching_sightings = [s for s in res["timeline"] if s["camera_id"] == "cam_11"]
        assert len(matching_sightings) >= 1
        assert any(snap_id in s["snapshot_url"] for s in matching_sightings)

        # 4. Check that get_history also returns timeline & snapshots
        hist = engine.get_history(session_id)
        assert len(hist["messages"]) >= 2  # user + assistant
        assistant_msg = [m for m in hist["messages"] if m["sender"] == "assistant"][-1]
        assert len(assistant_msg["timeline"]) >= 1
        assert any(snap_id in s["snapshot_url"] for s in assistant_msg["timeline"])

    finally:
        db.close()
