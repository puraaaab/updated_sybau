import os
import pytest
import tempfile
from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import Camera
from backend.services.bwc_ingest import BWCFileIngestService

def test_bwc_upload_ingest():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Create dummy temp file representing bodycam recording
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"dummy bodycam video content 12345")
            tmp_path = tmp.name

        res = BWCFileIngestService.process_bwc_upload(
            db=db,
            officer_id="OFF-9042",
            badge_number="B-108",
            device_serial="SN-BWC-99",
            file_path=tmp_path,
            original_filename="clip_001.mp4"
        )

        assert res["status"] == "success"
        assert res["camera_id"] == "bwc_sn-bwc-99"
        assert res["officer_id"] == "OFF-9042"
        assert os.path.exists(res["saved_path"])

        # Clean up created file and DB record
        if os.path.exists(res["saved_path"]):
            os.remove(res["saved_path"])
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
        from backend.database.models import Camera
        db.query(Camera).filter(Camera.id == "bwc_sn-bwc-99").delete()
        db.commit()
    finally:
        db.close()
