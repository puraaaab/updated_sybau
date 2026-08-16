import subprocess
import sys
from backend.database.connection import SessionLocal
from backend.database.models import Camera


def test_camera_deletion_persists_across_seeder_runs():
    db = SessionLocal()
    try:
        # Ensure at least 2 cameras exist
        cams = db.query(Camera).all()
        if not cams:
            # Run seeder once with --force
            subprocess.run([sys.executable, "backend/scripts/seed_rtsp_cams.py", "--force"], check=True)
            cams = db.query(Camera).all()

        initial_count = len(cams)
        assert initial_count > 0, "Cameras should exist after seed"

        # Pick one camera and delete it
        cam_to_delete = cams[-1]
        deleted_id = cam_to_delete.id
        db.delete(cam_to_delete)
        db.commit()

        count_after_del = db.query(Camera).count()
        assert count_after_del == initial_count - 1
        assert db.query(Camera).filter(Camera.id == deleted_id).first() is None

        # Simulate service restart running seed_rtsp_cams.py without --force
        res = subprocess.run([sys.executable, "backend/scripts/seed_rtsp_cams.py"], capture_output=True, text=True)
        assert res.returncode == 0
        assert "Preserving existing camera configuration" in res.stdout

        # Verify the deleted camera was NOT resurrected!
        assert db.query(Camera).count() == count_after_del
        assert db.query(Camera).filter(Camera.id == deleted_id).first() is None, "Deleted camera MUST remain deleted!"

    finally:
        db.close()
