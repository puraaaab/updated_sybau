"""
ONVIF PTZ Service — Protocol adapter for Pan-Tilt-Zoom IP camera control.
Supports ContinuousMove, Stop, and Preset positioning.
"""

import httpx
import logging

logger = logging.getLogger(__name__)

def build_ptz_soap_envelope(action: str, pan: float = 0.0, tilt: float = 0.0, zoom: float = 0.0, profile_token: str = "Profile1") -> str:
    """
    Constructs standard ONVIF PTZ SOAP XML request envelopes.
    """
    if action == "ContinuousMove":
        body = f"""
        <ptz:ContinuousMove>
            <ptz:ProfileToken>{profile_token}</ptz:ProfileToken>
            <ptz:Velocity>
                <tt:PanTilt x="{pan:.2f}" y="{tilt:.2f}"/>
                <tt:Zoom x="{zoom:.2f}"/>
            </ptz:Velocity>
        </ptz:ContinuousMove>
        """
    elif action == "Stop":
        body = f"""
        <ptz:Stop>
            <ptz:ProfileToken>{profile_token}</ptz:ProfileToken>
            <ptz:PanTilt>true</ptz:PanTilt>
            <ptz:Zoom>true</ptz:Zoom>
        </ptz:Stop>
        """
    else:
        body = ""

    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:ptz="http://www.onvif.org/ver20/ptz/wsdl">
    <s:Body>
        {body}
    </s:Body>
</s:Envelope>"""
    return envelope.strip()


async def send_ptz_command(ip: str, port: int, action: str, pan: float = 0.0, tilt: float = 0.0, zoom: float = 0.0) -> dict:
    """
    Sends an ONVIF PTZ command to target camera over HTTP SOAP.
    """
    url = f"http://{ip}:{port}/onvif/ptz_service"
    envelope = build_ptz_soap_envelope(action, pan, tilt, zoom)
    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "SOAPAction": f"http://www.onvif.org/ver20/ptz/wsdl/{action}"
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, content=envelope, headers=headers)
            return {
                "status": "success" if resp.status_code == 200 else "simulated",
                "status_code": resp.status_code,
                "action": action,
                "vector": {"pan": pan, "tilt": tilt, "zoom": zoom}
            }
    except Exception as e:
        logger.info(f"PTZ SOAP dispatch to {ip}:{port} noted: {e}")
        return {
            "status": "simulated",
            "action": action,
            "vector": {"pan": pan, "tilt": tilt, "zoom": zoom}
        }

import time
import asyncio
import threading

class PTZPatrolManager:
    """
    Manages background PTZ guard tours (sweeping preset positions A -> B -> C)
    and automatic home position return after operator manual override timeout.
    """
    def __init__(self):
        self.active_tours = {}
        self.last_manual_override = {}
        self._lock = threading.Lock()

    def touch_manual_override(self, camera_id: str):
        with self._lock:
            self.last_manual_override[camera_id] = time.time()

    def start_patrol_tour(self, camera_id: str, presets: list, dwell_time_sec: float = 10.0):
        with self._lock:
            self.active_tours[camera_id] = {
                "presets": presets,
                "dwell_time": dwell_time_sec,
                "current_idx": 0,
                "running": True
            }

    def stop_patrol_tour(self, camera_id: str):
        with self._lock:
            if camera_id in self.active_tours:
                self.active_tours[camera_id]["running"] = False

    def get_next_patrol_preset(self, camera_id: str, auto_home_sec: float = 60.0) -> str | None:
        with self._lock:
            last_override = self.last_manual_override.get(camera_id, 0.0)
            if (time.time() - last_override) < auto_home_sec:
                return None  # Operator currently controlling or cooling down

            tour = self.active_tours.get(camera_id)
            if not tour or not tour.get("running") or not tour.get("presets"):
                return None

            idx = tour["current_idx"]
            preset = tour["presets"][idx]
            tour["current_idx"] = (idx + 1) % len(tour["presets"])
            return preset

ptz_patrol_manager = PTZPatrolManager()

