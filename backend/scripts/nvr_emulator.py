import os
import subprocess
import time
import sys
import socket
from dotenv import load_dotenv

# Force stdout to flush immediately so logs appear in nvr.log
sys.stdout.reconfigure(line_buffering=True)

# Ensure backend modules are discoverable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env')))


def get_local_file_cameras():
    """Query the database for all active camera sources."""
    cams = []
    try:
        from backend.database.connection import SessionLocal
        from backend.database.models import Camera
        db = SessionLocal()
        try:
            db_cams = db.query(Camera).order_by(Camera.id).all()
            for c in db_cams:
                url = c.stream_url
                if not url:
                    continue
                lower = url.lower()
                if lower.startswith("http") or lower.startswith("rtsp://") or "youtube" in lower or "youtu.be" in lower:
                    continue
                normalized = url.replace("\\", "/")
                actual_path = normalized if os.path.isfile(normalized) else url
                cams.append((c.id, actual_path))
        finally:
            db.close()
    except Exception as e:
        print(f"[NVR] Dynamic DB camera lookup note: {e}")
        return None

    return cams


# Target ~30fps sources; keyframe every 1s keeps HLS/WHEP startup + live-edge latency low.
GOP_SECONDS = 1
FPS = 30
KEYFRAME_INTERVAL = GOP_SECONDS * FPS


def detect_best_encoder():
    # Prefer Windows Media Foundation (h264_mf) or libx264 to support 20+ concurrent streams
    # without hitting NVIDIA GeForce consumer driver concurrent session caps.
    for enc in ["h264_mf", "libx264", "h264_qsv", "h264_nvenc"]:
        try:
            res = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256", "-c:v", enc, "-frames:v", "1", "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if res.returncode == 0:
                return enc
        except Exception:
            pass
    return "libx264"

HW_ENCODER = detect_best_encoder()


def start_ffmpeg(video_path, rtsp_url, cam_id):
    # Select hardware GPU encoder (h264_nvenc / h264_mf) to offload 100% of encoding to GPU
    if HW_ENCODER == "h264_nvenc":
        vcodec_args = [
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-tune", "ull",
            "-b:v", "2000k",
            "-g", str(KEYFRAME_INTERVAL),
            "-pix_fmt", "yuv420p",
        ]
    elif HW_ENCODER == "h264_mf":
        vcodec_args = [
            "-c:v", "h264_mf",
            "-b:v", "1500k",
            "-g", str(KEYFRAME_INTERVAL),
            "-pix_fmt", "yuv420p",
        ]
    else:
        vcodec_args = [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-threads", "1",
            "-s", "640x360",
            "-b:v", "600k",
            "-pix_fmt", "yuv420p",
            "-g", str(KEYFRAME_INTERVAL),
        ]

    is_file = video_path and os.path.isfile(video_path)
    if is_file:
        input_args = [
            "-fflags", "+genpts+discardcorrupt",
            "-re",
            "-stream_loop", "-1",
            "-i", video_path,
            "-map", "0:v:0"
        ]
    else:
        input_args = ["-f", "lavfi", "-i", f"testsrc=size=1280x720:rate={FPS}"]

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-flags", "low_delay",
        "-err_detect", "ignore_err",
    ] + input_args + vcodec_args + [
        "-pix_fmt", "yuv420p",
        "-bf", "0",
        "-r", str(FPS),
        "-an",
        "-f", "rtsp", "-rtsp_transport", "tcp",
        rtsp_url
    ]

    return subprocess.Popen(
        cmd,
        stderr=None,
        stdout=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    print(f"Starting NVR Emulator on GPU Hardware Encoder ({HW_ENCODER})...")
    cameras = get_local_file_cameras()

    if not cameras:
        print("[NVR] No local file cameras found in database. Entering event-driven listener mode.")
        cameras = []

    print(f"[NVR] Found {len(cameras)} database camera(s) to broadcast.")
    processes = {}

    marker_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage', '.cameras_sync_event'))
    last_marker_mtime = os.path.getmtime(marker_file) if os.path.exists(marker_file) else 0

    # Setup non-blocking local UDP event receiver for instant zero-load IPC triggers
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 8555))
        sock.settimeout(2.0)
    except Exception as e:
        print(f"[NVR] Note: UDP sync listener bound with fallback: {e}")
        sock = None

    try:
        for cam_id, video_path in cameras:
            rtsp_url = f"rtsp://127.0.0.1:8554/{cam_id}"
            display_src = os.path.basename(video_path) if video_path else "synthetic testsrc"
            print(f"[NVR] Broadcasting {cam_id} -> {rtsp_url}  (src: {display_src}, enc: {HW_ENCODER})")
            p = start_ffmpeg(video_path, rtsp_url, cam_id)
            processes[cam_id] = {"proc": p, "path": video_path, "url": rtsp_url}
            time.sleep(0.1)

        print(f"\n[NVR] All {len(processes)} streams actively broadcasting on {HW_ENCODER}. Event-driven sync active.")

        def sync_active_streams():
            raw_cams = get_local_file_cameras()
            if raw_cams is not None:
                current_db_cams = dict(raw_cams)

                # Terminate streams for cameras that were deleted from DB
                for cid in list(processes.keys()):
                    if cid not in current_db_cams:
                        print(f"[NVR Event] Camera {cid} deleted from database. Terminating broadcast stream...")
                        try:
                            processes[cid]["proc"].terminate()
                        except Exception:
                            pass
                        del processes[cid]

                # Start streams for new cameras added to DB
                for cid, vpath in current_db_cams.items():
                    if cid not in processes:
                        r_url = f"rtsp://127.0.0.1:8554/{cid}"
                        print(f"[NVR Event] New camera {cid} added in database. Starting broadcast stream...")
                        p = start_ffmpeg(vpath, r_url, cid)
                        processes[cid] = {"proc": p, "path": vpath, "url": r_url}

        while True:
            trigger_sync = False
            # 1. Listen on UDP event socket
            if sock is not None:
                try:
                    data, _ = sock.recvfrom(1024)
                    if data:
                        trigger_sync = True
                except socket.timeout:
                    pass
                except Exception:
                    pass
            else:
                time.sleep(2.0)

            # 2. Check sync marker file change (O(1) inode stat, 0 DB queries)
            if not trigger_sync and os.path.exists(marker_file):
                try:
                    mtime = os.path.getmtime(marker_file)
                    if mtime > last_marker_mtime:
                        last_marker_mtime = mtime
                        trigger_sync = True
                except Exception:
                    pass

            # 3. Only perform DB query when an actual camera modification event happened
            if trigger_sync:
                sync_active_streams()

            # 4. Local fast in-memory process health check (0 DB load)
            for cid, info in list(processes.items()):
                if info["proc"].poll() is not None:
                    print(f"[NVR WARNING] Stream worker for {cid} exited (code {info['proc'].returncode}). Restarting...")
                    new_p = start_ffmpeg(info["path"], info["url"], cid)
                    processes[cid]["proc"] = new_p

    except KeyboardInterrupt:
        print("\n[NVR] Stopping all FFmpeg broadcast streams...")
        for cid, info in processes.items():
            try:
                info["proc"].terminate()
            except Exception:
                pass
        if sock:
            sock.close()
        print("[NVR] All streams stopped cleanly.")