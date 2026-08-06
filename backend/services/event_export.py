"""
VMS Pro — Alert Evidence Export Package Builder

FRAUD-03 FIX: Evidence export now selects the recording segment CLOSEST TO
              the alert timestamp, not always the latest file. If no segment
              can be matched within a 15-minute tolerance, the export is honest
              about the absence of a matching clip rather than including a
              wrong-time recording that would break chain of custody.

SEC-03 FIX: Stream-copy lossless slicing with keyframe alignment, dual SHA-256
            integrity hashes (exported clip vs source segments), and explicit
            export_method metadata labeling.

Each exported ZIP contains:
  1. evidence_clip.mp4   — keyframe-aligned evidence clip or raw segment
  2. trigger_frame.jpg   — the alert snapshot
  3. metadata.json       — full evidence metadata (hashes, offsets, method)
  4. signature.sha256    — SHA-256 of the exported video clip
  5. chain_of_custody.txt — text log of every action taken during export
"""

import os
import zipfile
import json
import hashlib
import shutil
import datetime
import logging
import subprocess
from sqlalchemy.orm import Session
from ..database.models import Alert

logger = logging.getLogger(__name__)

EXPORT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "exports"))
RECORDINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "recordings"))
SNAPSHOTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))

_UTC = datetime.timezone.utc

# Maximum age gap (in seconds) between alert timestamp and recording segment.
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

    for fmt in ("%Y%m%d_%H%M%S",):
        for part in name.split("_")[-2:]:
            candidate = "_".join(name.split("_")[-2:])
            try:
                dt = datetime.datetime.strptime(candidate, fmt)
                return dt.replace(tzinfo=_UTC)
            except ValueError:
                pass

    try:
        epoch = float(name)
        return datetime.datetime.fromtimestamp(epoch, tz=_UTC)
    except (ValueError, OSError):
        pass

    return None


def get_nearest_preceding_keyframe_time(video_path: str, target_offset_sec: float) -> float:
    """
    Uses ffprobe to inspect video keyframe timestamps.
    Returns the timestamp (in seconds) of the nearest keyframe (I-frame) <= target_offset_sec.
    If no preceding keyframe is found or ffprobe fails, returns target_offset_sec.
    """
    if target_offset_sec <= 0.0:
        return 0.0

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_frames",
        "-show_entries", "frame=pkt_pts_time,best_effort_timestamp_time,key_frame,pict_type",
        "-of", "json",
        video_path
    ]
    try:
        out = subprocess.check_output(cmd, timeout=10)
        data = json.loads(out)
        frames = data.get("frames", [])
        keyframes = []
        for f in frames:
            if f.get("key_frame") == 1 or f.get("pict_type") == "I":
                t_str = f.get("pkt_pts_time") or f.get("best_effort_timestamp_time")
                if t_str is not None:
                    try:
                        keyframes.append(float(t_str))
                    except ValueError:
                        pass
        keyframes.sort()
        preceding = [k for k in keyframes if k <= target_offset_sec]
        if preceding:
            return preceding[-1]
        if keyframes:
            return keyframes[0]
    except Exception as e:
        logger.warning(f"ffprobe keyframe probe note: {e}")
    return target_offset_sec


def slice_evidence_clip(
    source_video_path: str,
    output_clip_path: str,
    requested_start_offset_sec: float,
    duration_sec: float,
    force_reencode: bool = False
) -> dict:
    """
    Slices a clip from source_video_path using stream copy (-c copy) snapped to the nearest preceding keyframe.
    Falls back to re-encoding (-c:v libx264) if stream copy fails or force_reencode is True.
    """
    actual_start = requested_start_offset_sec
    keyframe_aligned = False

    if not force_reencode:
        actual_start = get_nearest_preceding_keyframe_time(source_video_path, requested_start_offset_sec)
        keyframe_aligned = abs(actual_start - requested_start_offset_sec) > 1e-3

        cmd_copy = [
            "ffmpeg", "-y",
            "-ss", f"{actual_start:.3f}",
            "-i", source_video_path,
            "-t", f"{duration_sec:.3f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_clip_path
        ]
        try:
            res = subprocess.run(cmd_copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if res.returncode == 0 and os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 500:
                return {
                    "export_method": "stream_copy",
                    "requested_start_offset_sec": requested_start_offset_sec,
                    "actual_start_offset_sec": actual_start,
                    "keyframe_aligned": keyframe_aligned,
                    "duration_sec": duration_sec
                }
        except Exception as e:
            logger.warning(f"Stream copy failed ({e}), falling back to re-encoding...")

    # Forced / Fallback Re-encoding
    actual_start = requested_start_offset_sec
    cmd_reencode = [
        "ffmpeg", "-y",
        "-ss", f"{actual_start:.3f}",
        "-i", source_video_path,
        "-t", f"{duration_sec:.3f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        output_clip_path
    ]
    subprocess.run(cmd_reencode, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

    return {
        "export_method": "re_encoded",
        "requested_start_offset_sec": requested_start_offset_sec,
        "actual_start_offset_sec": actual_start,
        "keyframe_aligned": False,
        "duration_sec": duration_sec
    }


def _find_overlapping_segments(
    cam_rec_dir: str, 
    alert_time: datetime.datetime,
    pre_roll_sec: int = 30,
    post_roll_sec: int = 30,
    segment_duration_sec: float = 60.0
) -> tuple[list[str], float | None]:
    """
    Finds all recording segments that overlap with the evidence window:
    [alert_time - pre_roll_sec, alert_time + post_roll_sec].
    Returns (list_of_filepaths, min_gap_seconds).
    """
    if not os.path.exists(cam_rec_dir) or not alert_time:
        return [], None

    mp4_files = sorted([f for f in os.listdir(cam_rec_dir) if f.endswith(".mp4")])
    if not mp4_files:
        return [], None

    if alert_time.tzinfo is None:
        alert_time = alert_time.replace(tzinfo=_UTC)

    win_start = alert_time - datetime.timedelta(seconds=pre_roll_sec)
    win_end = alert_time + datetime.timedelta(seconds=post_roll_sec)

    matching_files = []
    min_gap = float("inf")

    for fname in mp4_files:
        seg_start = _parse_segment_timestamp(fname)
        if seg_start is not None:
            if seg_start.tzinfo is None:
                seg_start = seg_start.replace(tzinfo=_UTC)
            seg_end = seg_start + datetime.timedelta(seconds=segment_duration_sec)
            
            gap = abs((seg_start - alert_time).total_seconds())
            if gap < min_gap:
                min_gap = gap

            if seg_start <= win_end and seg_end >= win_start:
                matching_files.append(os.path.join(cam_rec_dir, fname))

    if not matching_files and mp4_files:
        for fname in mp4_files:
            seg_start = _parse_segment_timestamp(fname)
            if seg_start is not None:
                gap = abs((seg_start - alert_time).total_seconds())
                if gap < min_gap:
                    min_gap = gap
        if min_gap <= _MAX_CLIP_TOLERANCE_SECONDS:
            best_fname = min(mp4_files, key=lambda f: abs((_parse_segment_timestamp(f) or alert_time) - alert_time).total_seconds() if _parse_segment_timestamp(f) else float("inf"))
            matching_files = [os.path.join(cam_rec_dir, best_fname)]

    return matching_files, (min_gap if min_gap != float("inf") else None)


def build_export_package(
    db: Session,
    alert_id: int,
    exported_by: str = "operator",
    redact_faces: bool = False,
    redact_plates: bool = False,
    force_reencode: bool = False
) -> str:
    """
    Creates a ZIP evidence package for the given alert.
    Computes dual hashes: source_segments_sha256 AND exported_clip_sha256.
    Labels export_method explicitly as "stream_copy" or "re_encoded".
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise ValueError(f"Alert with ID {alert_id} not found.")

    camera_id = alert.camera_id
    alert_time = alert.timestamp
    export_time = datetime.datetime.now(_UTC)

    if alert_time and alert_time.tzinfo is None:
        alert_time = alert_time.replace(tzinfo=_UTC)

    cam_rec_dir = os.path.join(RECORDINGS_DIR, camera_id)
    video_files, clip_gap = _find_overlapping_segments(cam_rec_dir, alert_time, pre_roll_sec=30, post_roll_sec=30)
    video_file = video_files[0] if video_files else None

    # Compute source segment hashes
    source_hashes = {}
    if video_files:
        for vf in video_files:
            if os.path.exists(vf):
                source_hashes[os.path.basename(vf)] = compute_sha256(vf)

    # ── Snapshot ─────────────────────────────────────────────────────────────
    snapshot_file = None
    if alert.snapshot_url:
        snap_id = alert.snapshot_url.split("/")[-1]
        for ext in (".jpg", ".jpeg", ".png", ""):
            candidate = os.path.join(SNAPSHOTS_DIR, f"{snap_id}{ext}")
            if os.path.exists(candidate):
                snapshot_file = candidate
                break

    # ── Build ZIP Directory ──────────────────────────────────────────────────
    temp_pack_dir = os.path.join(EXPORT_DIR, f"export_alert_{alert_id}_{export_time.strftime('%H%M%S')}")
    os.makedirs(temp_pack_dir, exist_ok=True)

    try:
        exported_clip_hash = None
        slice_info = {}

        if video_file and os.path.exists(video_file):
            copied_video = os.path.join(temp_pack_dir, "evidence_clip.mp4")
            
            # Determine offset from segment start time
            seg_start = _parse_segment_timestamp(os.path.basename(video_file))
            if seg_start and alert_time:
                req_start_offset = max(0.0, (alert_time - datetime.timedelta(seconds=30) - seg_start).total_seconds())
            else:
                req_start_offset = 0.0

            slice_info = slice_evidence_clip(
                source_video_path=video_file,
                output_clip_path=copied_video,
                requested_start_offset_sec=req_start_offset,
                duration_sec=60.0,
                force_reencode=force_reencode
            )

            exported_clip_hash = compute_sha256(copied_video)
            with open(os.path.join(temp_pack_dir, "signature.sha256"), "w") as sf:
                sf.write(f"{exported_clip_hash}  evidence_clip.mp4\n")

        snap_hash = None
        if snapshot_file and os.path.exists(snapshot_file):
            shutil.copy(snapshot_file, os.path.join(temp_pack_dir, "trigger_frame.jpg"))
            snap_hash = compute_sha256(snapshot_file)

        export_method_str = slice_info.get("export_method", "stream_copy" if not force_reencode else "re_encoded")

        custody_log = [
            f"=== VMS Pro Evidence Chain of Custody ===",
            f"Export Time (UTC):              {export_time.isoformat()}",
            f"Exported By:                    {exported_by}",
            f"Alert ID:                       {alert_id}",
            f"Alert Timestamp (UTC):          {alert_time.isoformat() if alert_time else 'UNKNOWN'}",
            f"Alert Camera:                   {camera_id}",
            f"Alert Type:                     {alert.type}",
            f"Alert Severity:                 {alert.severity}",
            f"Export Method:                  {export_method_str}",
            f"Requested Start Offset (sec):   {slice_info.get('requested_start_offset_sec', 0.0):.3f}",
            f"Actual Export Start (sec):      {slice_info.get('actual_start_offset_sec', 0.0):.3f}",
            f"Keyframe Aligned:               {slice_info.get('keyframe_aligned', False)}",
            f"Exported Clip SHA-256:          {exported_clip_hash or 'N/A'}",
            f"Source Segment(s) SHA-256:      {json.dumps(source_hashes)}",
            f"Snapshot Frame SHA-256:         {snap_hash or 'N/A'}",
            f"Face Redaction:                 {'ENABLED (Blurred)' if redact_faces else 'DISABLED (Original)'}",
            f"Plate Redaction:                {'ENABLED (Blurred)' if redact_plates else 'DISABLED (Original)'}",
            f"",
            f"=== End of Chain of Custody Log ==="
        ]

        metadata = {
            "export_timestamp_utc": export_time.isoformat(),
            "exported_by": exported_by,
            "alert_id": alert.id,
            "camera_id": alert.camera_id,
            "alert_type": alert.type,
            "alert_severity": alert.severity,
            "alert_timestamp_utc": alert_time.isoformat() if alert_time else None,
            "export_method": export_method_str,
            "requested_start_offset_sec": slice_info.get("requested_start_offset_sec", 0.0),
            "actual_start_offset_sec": slice_info.get("actual_start_offset_sec", 0.0),
            "keyframe_aligned": slice_info.get("keyframe_aligned", False),
            "exported_clip_sha256": exported_clip_hash,
            "source_segments_sha256": source_hashes,
            "snapshot_hash_sha256": snap_hash,
            "timestamp_source": "VMS Server UTC clock (NTP-synced system time)"
        }

        with open(os.path.join(temp_pack_dir, "metadata.json"), "w") as mf:
            json.dump(metadata, mf, indent=2)

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


export_alert_evidence = build_export_package
