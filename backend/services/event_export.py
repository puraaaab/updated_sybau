import os
import zipfile
import json
import hashlib
import shutil
import datetime
from sqlalchemy.orm import Session
from ..database.models import Alert

EXPORT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "exports"))
RECORDINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))
SNAPSHOTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))

def compute_sha256(filepath: str) -> str:
    """Computes the SHA-256 cryptographic hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def export_alert_evidence(alert_id: int, db: Session) -> str:
    """
    Creates a ZIP export package containing:
    1. The associated recorded video clip.
    2. The alert snapshot image.
    3. JSON metadata of the event.
    4. SHA-256 signature hash of the clip.
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise ValueError(f"Alert with ID {alert_id} not found.")
        
    camera_id = alert.camera_id
    alert_time = alert.timestamp
    
    # 1. Locate the video clip
    # Find files in storage/recordings/{camera_id}/
    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    video_file = None
    if os.path.exists(cam_rec_dir):
        files = sorted(os.listdir(cam_rec_dir))
        # Find segment closest to the alert timestamp
        # In a real VMS, we select segments containing the event. 
        # Here we pick the latest file or one closest to the alert timestamp.
        if files:
            video_file = os.path.join(cam_rec_dir, files[-1]) # default to latest for demo
            
    # 2. Locate the snapshot
    snapshot_file = None
    if alert.snapshot_url:
        snap_id = alert.snapshot_url.split("/")[-1]
        test_path = os.path.join(SNAPSHOTS_DIR, f"{snap_id}.jpg")
        if os.path.exists(test_path):
            snapshot_file = test_path
            
    # 3. Create metadata JSON content
    metadata = {
        "export_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "alert_id": alert.id,
        "camera_id": alert.camera_id,
        "type": alert.type,
        "message": alert.message,
        "severity": alert.severity,
        "alert_timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
        "chain_of_custody": "VMS Secure Forensic Export"
    }
    
    # Setup temporary directory for packing
    temp_pack_dir = os.path.join(EXPORT_DIR, f"export_alert_{alert_id}")
    os.makedirs(temp_pack_dir, exist_ok=True)
    
    try:
        # Copy files to temp packaging directory
        copied_video = None
        if video_file and os.path.exists(video_file):
            copied_video = os.path.join(temp_pack_dir, "evidence_clip.mp4")
            shutil.copy(video_file, copied_video)
            # Create SHA-256 signature
            sig_hash = compute_sha256(copied_video)
            with open(os.path.join(temp_pack_dir, "signature.sha256"), "w") as sf:
                sf.write(sig_hash)
            metadata["video_hash_sha256"] = sig_hash
            
        if snapshot_file and os.path.exists(snapshot_file):
            shutil.copy(snapshot_file, os.path.join(temp_pack_dir, "trigger_frame.jpg"))
            
        # Write metadata
        with open(os.path.join(temp_pack_dir, "metadata.json"), "w") as mf:
            json.dump(metadata, mf, indent=2)
            
        # Zip everything
        zip_filename = f"evidence_alert_{alert_id}.zip"
        zip_path = os.path.join(EXPORT_DIR, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_pack_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), file)
                    
        return zip_path
        
    finally:
        # Clean up temp folder
        if os.path.exists(temp_pack_dir):
            shutil.rmtree(temp_pack_dir)

def datetime_now():
    import datetime
    return datetime.datetime.utcnow()

def datetime_to_iso(dt):
    return dt.isoformat() if dt else None
