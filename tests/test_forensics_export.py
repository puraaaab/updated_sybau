import os
import json
import zipfile
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from backend.main import app
from backend.database.models import Base, Alert
from backend.services import event_export

client = TestClient(app)

def get_auth_header():
    res = client.post("/api/v1/auth/login", data={"username": "admin", "password": "Admin@123456"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_create_forensic_export_endpoint():
    headers = get_auth_header()
    # Create test recording segment inside storage/recordings/cyber_cam_6
    storage_rec_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "recordings", "cyber_cam_6"))
    os.makedirs(storage_rec_dir, exist_ok=True)
    sample_file = os.path.join(storage_rec_dir, "20260812_120000.mp4")
    if not os.path.exists(sample_file):
        with open(sample_file, "wb") as f:
            f.write(b"HEADER_DUMMY_MP4_RECORDING_DATA_" + b"0" * 100000)

    response = client.post("/api/v1/forensics/export?camera_id=cyber_cam_6", headers=headers)


    assert response.status_code == 200
    data = response.json()
    assert "export_filename" in data
    assert "sha256_hash" in data
    assert "download_url" in data

def test_get_forensic_exports_ledger():
    headers = get_auth_header()
    response = client.get("/api/v1/forensics/exports", headers=headers)
    assert response.status_code == 200
    ledger = response.json()
    assert isinstance(ledger, list)

def test_build_export_package_dual_hashes_and_method():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    from backend.utils.timezone import get_ist_now
    _now = get_ist_now()
    alert = Alert(
        camera_id="cam_test_export",
        type="loitering",
        message="Test alert for export package",
        severity="high",
        timestamp=_now
    )
    db.add(alert)
    db.commit()

    # 1. Test stream_copy path (or no clip fallback)
    zip_path = event_export.build_export_package(db, alert.id, exported_by="test_admin", force_reencode=False)
    assert os.path.exists(zip_path)
    assert zip_path.endswith(".zip")

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "metadata.json" in namelist
        assert "chain_of_custody.txt" in namelist

        with zf.open("metadata.json") as mf:
            meta = json.load(mf)
            assert "export_method" in meta
            assert meta["export_method"] in ("stream_copy", "re_encoded")
            assert "source_segments_sha256" in meta
            assert "exported_clip_sha256" in meta

        with zf.open("chain_of_custody.txt") as cf:
            custody_text = cf.read().decode("utf-8")
            assert "Export Method:" in custody_text
            assert "Exported Clip SHA-256:" in custody_text
            assert "Source Segment(s) SHA-256:" in custody_text

    # 2. Test forced re-encode path
    zip_path_reencode = event_export.build_export_package(db, alert.id, exported_by="test_admin", force_reencode=True)
    assert os.path.exists(zip_path_reencode)

    with zipfile.ZipFile(zip_path_reencode, "r") as zf:
        with zf.open("metadata.json") as mf:
            meta_re = json.load(mf)
            # When forced, or when no source clip exists, export_method is explicitly documented
            assert "export_method" in meta_re
