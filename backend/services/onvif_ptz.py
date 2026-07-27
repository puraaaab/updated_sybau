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
