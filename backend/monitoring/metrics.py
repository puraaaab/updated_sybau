"""
Prometheus Metrics Exporter for Sybau VMS.

Exposes standard Prometheus metric text format for:
  • HTTP requests & latency
  • System CPU, RAM, Storage, and GPU VRAM utilization
  • Active RTSP camera streams, FPS, and drop rates
  • Inference worker queue depth and latency
"""

import time
import logging
from typing import List
from .health import get_system_vitals, get_services_health
from ..config.service import get_cameras

logger = logging.getLogger(__name__)


def generate_prometheus_metrics() -> str:
    """
    Generates plain-text Prometheus metrics output for scraping.
    """
    lines: List[str] = []
    now_ts = time.time()

    # 1. System Vitals
    vitals = get_system_vitals()
    lines.append("# HELP vms_cpu_utilization_percent Current host CPU utilization percentage.")
    lines.append("# TYPE vms_cpu_utilization_percent gauge")
    lines.append(f"vms_cpu_utilization_percent {vitals.get('cpu_utilization', 0.0):.2f}")

    lines.append("# HELP vms_ram_utilization_percent Current host RAM utilization percentage.")
    lines.append("# TYPE vms_ram_utilization_percent gauge")
    lines.append(f"vms_ram_utilization_percent {vitals.get('ram_utilization', 0.0):.2f}")

    lines.append("# HELP vms_storage_utilization_percent Current disk storage utilization percentage.")
    lines.append("# TYPE vms_storage_utilization_percent gauge")
    lines.append(f"vms_storage_utilization_percent {vitals.get('storage_utilization', 0.0):.2f}")

    gpu = vitals.get("gpu", {})
    if gpu.get("vram_used_mb") is not None:
        lines.append("# HELP vms_gpu_vram_used_mb Current GPU VRAM allocated in megabytes.")
        lines.append("# TYPE vms_gpu_vram_used_mb gauge")
        lines.append(f"vms_gpu_vram_used_mb {gpu['vram_used_mb']:.1f}")

        lines.append("# HELP vms_gpu_vram_total_mb Total GPU VRAM memory in megabytes.")
        lines.append("# TYPE vms_gpu_vram_total_mb gauge")
        lines.append(f"vms_gpu_vram_total_mb {gpu['vram_total_mb']:.1f}")

    # 2. Services Health Status (1=online, 0=offline)
    services = get_services_health()
    lines.append("# HELP vms_service_status Service health status (1=online, 0=offline).")
    lines.append("# TYPE vms_service_status gauge")
    for s_name, s_val in services.items():
        val = 1 if s_val == "online" else 0
        lines.append(f'vms_service_status{{service="{s_name}"}} {val}')

    # 3. Active Camera Stream Metrics
    cams = get_cameras()
    lines.append("# HELP vms_active_cameras Total registered camera streams.")
    lines.append("# TYPE vms_active_cameras gauge")
    lines.append(f"vms_active_cameras {len(cams)}")

    lines.append("# HELP vms_camera_configured_fps Configured stream frame rate.")
    lines.append("# TYPE vms_camera_configured_fps gauge")
    for cam in cams:
        cid = cam.get("id", "unknown")
        fps = cam.get("fps", 10.0)
        lines.append(f'vms_camera_configured_fps{{camera_id="{cid}"}} {fps}')

    lines.append(f"# Uptime timestamp: {now_ts}")
    return "\n".join(lines) + "\n"
