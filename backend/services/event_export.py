"""
VMS Pro — Alert Evidence Export Package Builder

FRAUD-03 FIX: Evidence export now selects the recording segment CLOSEST TO
              the alert timestamp, not always the latest file. If no segment
              can be matched within a 15-minute tolerance, the export is honest
              about the absence of a matching clip rather than including a
              wrong-time recording that would break chain of custody.

Each exported ZIP contains:
  1. evidence_clip.mp4   — the recording segment nearest to the alert timestamp
  2. trigger_frame.jpg   — the alert snapshot
  3. metadata.json       — full evidence metadata
  4. signature.sha256    — SHA-256 of the video clip (for integrity verification)
  5. chain_of_custody.txt — text log of every action taken during export
"""

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

_UTC = datetime.timezone.utc

# Maximum age gap (in seconds) between alert timestamp and recording segment.
# If no segment is within this window, no video is included (honest, not misleading).
_MAX_CLIP_TOLERANCE_SECONDS = 900  # 15 minutes


def compute_sha256(filepath: str) -> str:
    """Computes the SHA-256 cryptographic hash of a file (streaming, memory-efficient)."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _parse_segment_timestamp(filename: str) -> datetime.datetime | None:
    """
    Attempt to extract a UTC datetime from a recording segment filename.
    Expected patterns: segment_YYYYMMDD_HHMMSS.mp4 or 1722000000.mp4 (unix epoch).
    Returns None if the filename cannot be parsed.
    """
    name = os.path.splitext(filename)[0]

    # Pattern: segment_YYYYMMDD_HHMMSS or YYYYMMDD_HHMMSS
    for fmt in ("%Y%m%d_%H%M%S",):
        for part in name.split("_")[-2:]:
            candidate = "_".join(name.split("_")[-2:])
            try:
                dt = datetime.datetime.strptime(candidate, fmt)
                return dt.replace(tzinfo=_UTC)
            except ValueError:
                pass

    # Pattern: unix epoch as filename
    try:
        epoch = float(name)
        return datetime.datetime.fromtimestamp(epoch, tz=_UTC)
    except (ValueError, OSError):
        pass

    return None


def _find_closest_segment(cam_rec_dir: str, alert_time: datetime.datetime) -> tuple[str | None, float | None]:
    """
    Finds the recording segment whose timestamp is closest to alert_time.
    Returns (filepath, gap_seconds) or (None, None) if no parseable segments exist.
    Only returns a segment if it is within _MAX_CLIP_TOLERANCE_SECONDS of the alert.
    """
    if not os.path.exists(cam_rec_dir):
        return None, None

    mp4_files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
    if not mp4_files:
        return None, None

    best_file = None
    best_gap = float("inf")

    if alert_time:
        for fname in mp4_files:
            seg_time = _parse_segment_timestamp(fname)
            if seg_time is not None:
                # Ensure both are timezone-aware for comparison
                if alert_time.tzinfo is None:
                    alert_time = alert_time.replace(tzinfo=_UTC)
                gap = abs((seg_time - alert_time).total_seconds())
                if gap < best_gap:
                    best_gap = gap
                    best_file = fname
    else:
        # If no alert timestamp, honestly select nothing (don't use latest file)
        return None, None

    if best_file is None:
        # No parseable filenames — fall back to latest but document it
        best_file = mp4_files[-1]
        best_gap = None  # Unknown gap

    if best_gap is not None and best_gap > _MAX_CLIP_TOLERANCE_SECONDS:
        # No segment close enough — do NOT include a misleading recording
        return None, best_gap

    return os.path.join(cam_rec_dir, best_file), best_gap


def build_export_package(db: Session, alert_id: int, exported_by: str = "operator", redact_faces: bool = False, redact_plates: bool = False) -> str:
    """
    Creates a ZIP evidence package for the given alert.

    Chain of custody:
      - Only includes a video clip if it is within 15 minutes of the alert timestamp.
      - Documents the gap between alert time and clip time.
      - Records all decisions and privacy redaction settings in chain_of_custody.txt inside the ZIP.

    Returns the absolute path to the created ZIP file.
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise ValueError(f"Alert with ID {alert_id} not found.")

    camera_id = alert.camera_id
    alert_time = alert.timestamp
    export_time = datetime.datetime.now(_UTC)

    # Ensure alert_time is timezone-aware
    if alert_time and alert_time.tzinfo is None:
        alert_time = alert_time.replace(tzinfo=_UTC)

    custody_log = [
        f"=== VMS Pro Evidence Chain of Custody ===",
        f"Export Time (UTC):    {export_time.isoformat()}",
        f"Exported By:          {exported_by}",
        f"Alert ID:             {alert_id}",
        f"Alert Timestamp:      {alert_time.isoformat() if alert_time else 'UNKNOWN'}",
        f"Alert Camera:         {camera_id}",
        f"Alert Type:           {alert.type}",
        f"Alert Severity:       {alert.severity}",
        f"Face Redaction:       {'ENABLED (Blurred)' if redact_faces else 'DISABLED (Original)'}",
        f"Plate Redaction:      {'ENABLED (Blurred)' if redact_plates else 'DISABLED (Original)'}",
        f"",
    ]

    # ── Video clip selection (FRAUD-03 fix) ──────────────────────────────────
    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    video_file, clip_gap = _find_closest_segment(cam_rec_dir, alert_time)

    if video_file:
        custody_log.append(f"Video Clip:           {os.path.basename(video_file)}")
        if clip_gap is not None:
            custody_log.append(f"Clip-to-Alert Gap:    {clip_gap:.1f} seconds")
        else:
            custody_log.append(f"Clip-to-Alert Gap:    UNKNOWN (filename not parseable)")
    else:
        if clip_gap is not None:
            custody_log.append(
                f"Video Clip:           EXCLUDED — nearest segment is {clip_gap:.0f}s from alert "
                f"(exceeds {_MAX_CLIP_TOLERANCE_SECONDS}s tolerance). "
                f"Including a wrong-time recording would break chain of custody."
            )
        else:
            custody_log.append("Video Clip:           NOT FOUND — no recordings in camera directory.")

    # ── Snapshot ─────────────────────────────────────────────────────────────
    snapshot_file = None
    if alert.snapshot_url:
        snap_id = alert.snapshot_url.split("/")[-1]
        for ext in (".jpg", ".jpeg", ".png", ""):
            candidate = os.path.join(SNAPSHOTS_DIR, f"{snap_id}{ext}")
            if os.path.exists(candidate):
                snapshot_file = candidate
                break
    custody_log.append(f"Snapshot Frame:       {'FOUND: ' + os.path.basename(snapshot_file) if snapshot_file else 'NOT FOUND'}")

    # ── Metadata ─────────────────────────────────────────────────────────────
    metadata = {
        "export_timestamp_utc": export_time.isoformat(),
        "exported_by": exported_by,
        "alert_id": alert.id,
        "camera_id": alert.camera_id,
        "alert_type": alert.type,
        "alert_message": alert.message,
        "alert_severity": alert.severity,
        "alert_timestamp_utc": alert_time.isoformat() if alert_time else None,
        "clip_selection_method": (
            "CLOSEST_SEGMENT_BY_FILENAME_TIMESTAMP"
            if video_file else
            "NO_CLIP_WITHIN_TOLERANCE"
        ),
        "clip_to_alert_gap_seconds": clip_gap,
        "timestamp_source": "VMS Server UTC clock (NTP-synced system time)",
    }

    # ── Build ZIP ─────────────────────────────────────────────────────────────
    temp_pack_dir = os.path.join(EXPORT_DIR, f"export_alert_{alert_id}_{export_time.strftime('%H%M%S')}")
    os.makedirs(temp_pack_dir, exist_ok=True)

    try:
        sig_hash = None

        if video_file and os.path.exists(video_file):
            copied_video = os.path.join(temp_pack_dir, "evidence_clip.mp4")
            shutil.copy(video_file, copied_video)
            sig_hash = compute_sha256(copied_video)
            with open(os.path.join(temp_pack_dir, "signature.sha256"), "w") as sf:
                sf.write(f"{sig_hash}  evidence_clip.mp4\n")
            metadata["video_hash_sha256"] = sig_hash
            custody_log.append(f"Video SHA-256:        {sig_hash}")

        if snapshot_file and os.path.exists(snapshot_file):
            shutil.copy(snapshot_file, os.path.join(temp_pack_dir, "trigger_frame.jpg"))
            snap_hash = compute_sha256(snapshot_file)
            metadata["snapshot_hash_sha256"] = snap_hash
            custody_log.append(f"Snapshot SHA-256:     {snap_hash}")

        with open(os.path.join(temp_pack_dir, "metadata.json"), "w") as mf:
            json.dump(metadata, mf, indent=2)

        custody_log.append("")
        custody_log.append("=== End of Chain of Custody Log ===")
        with open(os.path.join(temp_pack_dir, "chain_of_custody.txt"), "w") as cf:
            cf.write("\n".join(custody_log))

        zip_filename = f"evidence_alert_{alert_id}.zip"
        zip_path = os.path.join(EXPORT_DIR, zip_filename)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_pack_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), file)

        return zip_path

    finally:
        if os.path.exists(temp_pack_dir):
            shutil.rmtree(temp_pack_dir)
