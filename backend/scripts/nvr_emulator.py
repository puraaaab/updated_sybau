import os
import subprocess
import time
import sys

# Force stdout to flush immediately so logs appear in nvr.log (pipe buffering fix)
sys.stdout.reconfigure(line_buffering=True)

# Ensure the backend module is discoverable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# ---------------------------------------------------------------------------
# Load all cameras from the database and publish local file sources to
# MediaMTX via RTSP so that MediaMTX can serve them as HLS streams.
#
# Each camera whose stream_url is a local file path gets published to:
#   rtsp://127.0.0.1:8554/{camera_id}
# MediaMTX then exposes it as:
#   http://localhost:8888/{camera_id}/index.m3u8  (HLS)
# ---------------------------------------------------------------------------

def get_local_file_cameras():
    """Query the DB for cameras whose source is a local file path."""
    try:
        from backend.database.connection import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, stream_url FROM cameras WHERE stream_url IS NOT NULL"
            )).fetchall()
        result = []
        for row in rows:
            cam_id, url = row[0], row[1]
            if not url:
                continue
            # Skip YouTube / HTTP / RTSP external sources — only local files
            lower = url.lower()
            if lower.startswith("http") or lower.startswith("rtsp://") or "youtube" in lower or "youtu.be" in lower:
                continue
            # Normalize Windows path separators
            normalized = url.replace("\\", "/")
            if os.path.isfile(normalized) or os.path.isfile(url):
                actual_path = normalized if os.path.isfile(normalized) else url
                result.append((cam_id, actual_path))
            else:
                print(f"[NVR] Warning: file not found for camera {cam_id}: {url}")
        return result
    except Exception as e:
        print(f"[NVR] DB lookup failed, falling back to static list: {e}")
        return _static_fallback()


def _static_fallback():
    """Original static list as a fallback if DB is unavailable."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Videos'))
    entries = [
        ("cam_1", "Export__Central Bus Depo-Entry Gate Platform Area_Friday July 10 2026110138  b33bb2a.avi"),
        ("cam_2", "Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714 (1).avi"),
        ("cam_3", "Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714.avi"),
        ("cam_4", "Export__Gopi Talav-Towards Gopi Talav Gate_Friday July 10 202661000  dc1f515.avi"),
        ("cam_5", "Export__Mahidharpura-Pipla Sheri Diamond Mkt_Friday July 10 202655441  beb5fa4.avi"),
        ("cam_6", "Export__Rly Station-Towards Bismillah Rest left_Friday July 10 202661242  09a94cc.avi"),
        ("cam_7", "merged.mp4"),
    ]
    return [
        (cam_id, os.path.join(base_dir, filename))
        for cam_id, filename in entries
        if os.path.isfile(os.path.join(base_dir, filename))
    ]


# Target ~30fps sources; keyframe every 1s keeps HLS/WHEP startup + live-edge latency low.
GOP_SECONDS = 1
FPS = 30
KEYFRAME_INTERVAL = GOP_SECONDS * FPS


def check_nvenc_support():
    try:
        res = subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=256x256", "-c:v", "h264_nvenc", "-frames:v", "1", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False

HAS_NVENC = check_nvenc_support()

def start_ffmpeg(video_path, rtsp_url, cam_id):
    vcodec_args = [
        "-c:v", "h264_nvenc",
        "-preset", "p1",
        "-tune", "ll",
        "-b:v", "1500k",
        "-maxrate", "1500k",
        "-bufsize", "1500k",
    ] if HAS_NVENC else [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-b:v", "1M",
        "-maxrate", "1M",
        "-bufsize", "1M",
    ]

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-fflags", "+genpts+igndts",
        "-err_detect", "ignore_err",
        "-re", "-stream_loop", "-1", "-i", video_path,
    ] + vcodec_args + [
        "-g", str(KEYFRAME_INTERVAL),
        "-bf", "0",
        "-forced-idr", "1",
        "-r", str(FPS),
        "-an",
        "-f", "rtsp", "-rtsp_transport", "tcp",
        rtsp_url
    ]

    return subprocess.Popen(
        cmd,
        stderr=None,        # inherit parent's stderr (flows to nvr.log)
        stdout=subprocess.DEVNULL,
    )


print("Starting NVR Emulator... Loading camera sources from database.")
cameras = get_local_file_cameras()

if not cameras:
    print("[NVR] No local file cameras found in database. Exiting.")
    sys.exit(0)

print(f"[NVR] Found {len(cameras)} local-file camera(s) to broadcast.")
processes = []

try:
    for cam_id, video_path in cameras:
        rtsp_url = f"rtsp://127.0.0.1:8554/{cam_id}"
        p = start_ffmpeg(video_path, rtsp_url, cam_id)
        processes.append({"cam_id": cam_id, "p": p, "url": rtsp_url, "path": video_path})
        print(f"[NVR] Broadcasting {cam_id} -> {rtsp_url}  (src: {os.path.basename(video_path)})")
        time.sleep(0.5)  # Stagger startup to avoid MediaMTX path-registration races

    print("\n[NVR] All streams actively broadcasting. Press Ctrl+C to stop.")

    # Keep main thread alive and watch for crashed processes
    while True:
        time.sleep(2)
        for state in processes:
            if state["p"].poll() is not None:
                exit_code = state["p"].returncode
                print(f"[NVR] {state['cam_id']} died (exit={exit_code}). Restarting in 3s...")
                time.sleep(3)
                state["p"] = start_ffmpeg(state["path"], state["url"], state["cam_id"])
                print(f"[NVR] {state['cam_id']} restarted.")

except KeyboardInterrupt:
    print("\n[NVR] Shutting down streams...")
    for state in processes:
        if state["p"].poll() is None:
            state["p"].terminate()
    print("[NVR] Shutdown complete.")