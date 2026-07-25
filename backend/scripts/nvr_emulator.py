import os
import subprocess
import time
import sys

# Force stdout to flush immediately so logs appear in nvr.log (pipe buffering fix)
sys.stdout.reconfigure(line_buffering=True)

# Ensure the backend module is discoverable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Videos'))
videos = [
    os.path.join(base_dir, "Export__Central Bus Depo-Entry Gate Platform Area_Friday July 10 2026110138  b33bb2a.avi"),
    os.path.join(base_dir, "Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714 (1).avi"),
    os.path.join(base_dir, "Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714.avi"),
    os.path.join(base_dir, "Export__Gopi Talav-Towards Gopi Talav Gate_Friday July 10 202661000  dc1f515.avi"),
    os.path.join(base_dir, "Export__Mahidharpura-Pipla Sheri Diamond Mkt_Friday July 10 202655441  beb5fa4.avi"),
    os.path.join(base_dir, "Export__Rly Station-Towards Bismillah Rest left_Friday July 10 202661242  09a94cc.avi"),
    os.path.join(base_dir, "merged.mp4")
]

processes = []

# Target ~30fps sources; keyframe every 1s keeps HLS/WHEP startup + live-edge latency low.
GOP_SECONDS = 1
FPS = 30
KEYFRAME_INTERVAL = GOP_SECONDS * FPS


def start_ffmpeg(video_path, stream_url, cam_idx):
    return subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            # AVI/H264 loop boundary tolerance: regenerate timestamps and ignore
            # DTS gaps that appear at loop points in raw AVI streams.
            "-fflags", "+genpts+igndts",
            "-err_detect", "ignore_err",
            "-re", "-stream_loop", "-1", "-i", video_path,

            # --- Low-latency CPU encode settings ---
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-b:v", "2M",
            "-maxrate", "2M",
            "-bufsize", "2M",               # small bufsize = encoder can't hoard frames
            "-g", str(KEYFRAME_INTERVAL),   # short GOP: keyframe every ~1s
            "-bf", "0",                     # no B-frames (they need future frames = delay)
            "-forced-idr", "1",
            "-r", str(FPS),                 # constant frame rate, avoids PTS drift/stutter
            "-an",

            "-f", "rtsp", "-rtsp_transport", "tcp",
            stream_url
        ],
        stderr=None,        # inherit parent's stderr (flows to nvr.log)
        stdout=subprocess.DEVNULL,
    )


print("Starting NVR Emulator... Broadcasting local CCTV footage as live RTSP streams to MediaMTX.")

try:
    for idx, video_path in enumerate(videos, start=1):
        if not os.path.exists(video_path):
            print(f"Warning: Video file not found: {video_path}")
            continue
        stream_url = f"rtsp://127.0.0.1:8554/cam_{idx}"
        p = start_ffmpeg(video_path, stream_url, idx)
        processes.append({"idx": idx, "p": p, "url": stream_url, "path": video_path})
        print(f"[NVR] Started broadcasting Camera {idx} -> {stream_url}")
        time.sleep(0.5)  # Stagger startup to avoid MediaMTX path-registration races

    print("\n[NVR] All streams are actively broadcasting. Press Ctrl+C to stop.")

    # Keep main thread alive and watch for crashed processes
    while True:
        time.sleep(2)
        for state in processes:
            if state["p"].poll() is not None:
                # Process died (e.g. MediaMTX restarted) — wait briefly then reconnect
                exit_code = state["p"].returncode
                print(f"[NVR] Stream {state['idx']} died (exit={exit_code}). Restarting in 3s...")
                time.sleep(3)
                state["p"] = start_ffmpeg(state["path"], state["url"], state["idx"])
                print(f"[NVR] Stream {state['idx']} restarted.")

except KeyboardInterrupt:
    print("\n[NVR] Shutting down streams...")
    for state in processes:
        if state["p"].poll() is None:
            state["p"].terminate()
    print("[NVR] Shutdown complete.")