import os
import json
import socket
import time
import cv2
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database.connection import get_db
from ..database.models import Camera, Zone, AlertConfig
from ..auth.helpers import verify_admin, verify_operator, verify_viewer
from ..config import service as config_service
from ..recording import recorder
from ..workers import ai_worker
from ..services.stream_resolver import resolve_stream_url, is_youtube_url
from ..services.stream_manager import stream_manager
from ..config.service import get_models

import defusedxml.ElementTree as ET

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get("")
def get_cameras(user=Depends(verify_viewer), db: Session = Depends(get_db)):
    cams = db.query(Camera).all()
    result = []
    for c in cams:
        telem = ai_worker.get_latest_telemetry(c.id) or {}
        cam_dict = {
            "id": c.id,
            "name": c.name,
            "location": c.location or "Unknown",
            "stream_url": c.stream_url,
            "status": c.status,
            "width": c.width,
            "height": c.height,
            "motion_status": telem.get("motion_status", "STREAMING"),
            "fps": telem.get("fps", 2.0)
        }
        raw = c.stream_url or ""
        is_youtube = "youtube.com" in raw or "youtu.be" in raw
        if is_youtube:
            cam_dict["hls_url"] = raw
            cam_dict["is_youtube"] = True
        else:
            cam_dict["hls_url"] = f"http://localhost:8888/{c.id}/index.m3u8"
            cam_dict["is_youtube"] = False
        result.append(cam_dict)
    return result


@router.post("/scan")
def scan_onvif_cameras(user=Depends(verify_viewer)):
    ws_probe = """<?xml version="1.0" encoding="UTF-8"?>
    <e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
                xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
                xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
      <e:Header>
        <w:MessageID>uuid:84576391-4b3e-4c72-91ef-75210214a1a0</w:MessageID>
        <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
        <w:Action>http://schemas.xmlsoap.org/ws/2005:04:discovery/Probe</w:Action>
      </e:Header>
      <e:Body>
        <d:Probe>
          <d:Types>dn:NetworkVideoTransmitter</d:Types>
        </d:Probe>
      </e:Body>
    </e:Envelope>"""
    
    discovered_real = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(1.5)
        sock.sendto(ws_probe.encode('utf-8'), ('239.255.255.250', 3702))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if not any(d['ip'] == ip for d in discovered_real):
                    discovered_real.append({
                        "name": f"ONVIF Camera ({ip})",
                        "ip": ip,
                        "port": 80,
                        "mac": f"00:1A:2B:3C:4D:{len(discovered_real)+1:02d}"
                    })
            except socket.timeout:
                break
        sock.close()
    except Exception as e:
        pass

    devices = discovered_real
    if len(devices) == 0:
        cfg = get_models()
        if cfg.get("demo_mode", False):
            devices = [
                {"name": "Hikvision NVR Channel 1", "ip": "192.168.1.101", "port": 80, "mac": "00:1A:2B:3C:4D:01"},
                {"name": "Dahua Body-Worn Cam Relay", "ip": "192.168.1.102", "port": 80, "mac": "00:1A:2B:3C:4D:02"},
                {"name": "Axis Dome Camera P3245", "ip": "192.168.1.103", "port": 80, "mac": "00:1A:2B:3C:4D:03"},
                {"name": "CP PLUS Speed Dome", "ip": "192.168.1.104", "port": 80, "mac": "00:1A:2B:3C:4D:04"}
            ]
    return {"status": "success", "count": len(devices), "is_real": len(discovered_real) > 0, "devices": devices}


@router.post("/resolve-onvif")
def resolve_onvif_stream_uri(payload: dict, user=Depends(verify_viewer)):
    ip = payload.get("onvif_ip", "127.0.0.1")
    port = payload.get("onvif_port", 80)
    uname = payload.get("onvif_username", "admin")
    pwd = payload.get("onvif_password", "")
    
    rtsp_url = f"rtsp://{uname}:{pwd}@{ip}:554/live/ch0" if pwd else f"rtsp://{ip}:554/live/ch0"
    is_real = False

    try:
        from onvif import ONVIFCamera
        mycam = ONVIFCamera(ip, port, uname, pwd)
        media_service = mycam.create_media_service()
        profiles = media_service.GetProfiles()
        if profiles:
            token = profiles[0].token
            obj = media_service.create_type('GetStreamUri')
            obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
            obj.ProfileToken = token
            res = media_service.GetStreamUri(obj)
            if res and hasattr(res, 'Uri'):
                rtsp_url = res.Uri
                is_real = True
    except Exception:
        pass

    return {
        "status": "success",
        "onvif_ip": ip,
        "stream_url": rtsp_url,
        "is_real_soap": is_real
    }


@router.post("")
def add_camera(camera: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    existing = db.query(Camera).filter(Camera.id == camera["id"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="Camera ID already exists")

    new_cam = Camera(
        id=camera["id"],
        name=camera["name"],
        location=camera.get("location", "Unknown"),
        stream_url=camera["stream_url"],
        status="connecting",
        width=camera.get("width", 1920),
        height=camera.get("height", 1080)
    )
    db.add(new_cam)

    default_cfg = AlertConfig(
        camera_id=camera["id"],
        loitering_seconds=10,
        running_speed_threshold=150.0,
        crowd_density_threshold=5
    )
    db.add(default_cfg)
    db.commit()

    if camera["id"] not in recorder.active_recorders:
        rec = recorder.CameraRecorder(camera["id"], camera["stream_url"])
        recorder.active_recorders[camera["id"]] = rec
        rec.start()

    if camera["id"] not in ai_worker.active_ai_workers:
        worker = ai_worker.CameraAIWorker(camera["id"], camera["stream_url"])
        ai_worker.active_ai_workers[camera["id"]] = worker
        worker.start()

    return {"message": "Camera added and workers spawned successfully"}


@router.put("/{camera_id}")
def update_camera(camera_id: str, camera: dict, user=Depends(verify_admin), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    old_url = cam.stream_url
    cam.name = camera.get("name", cam.name)
    cam.location = camera.get("location", cam.location)
    cam.stream_url = camera.get("stream_url", cam.stream_url)
    cam.width = camera.get("width", cam.width)
    cam.height = camera.get("height", cam.height)
    
    db.commit()
    db.refresh(cam)

    if old_url != cam.stream_url:
        if camera_id in recorder.active_recorders:
            recorder.active_recorders[camera_id].stop()
            del recorder.active_recorders[camera_id]
        if camera_id in ai_worker.active_ai_workers:
            ai_worker.active_ai_workers[camera_id].stop()
            del ai_worker.active_ai_workers[camera_id]
            
        rec = recorder.CameraRecorder(camera_id, cam.stream_url)
        recorder.active_recorders[camera_id] = rec
        rec.start()

        worker = ai_worker.CameraAIWorker(camera_id, cam.stream_url)
        ai_worker.active_ai_workers[camera_id] = worker
        worker.start()
        
    return {"message": "Camera updated successfully"}


@router.delete("/{camera_id}")
def delete_camera(camera_id: str, user=Depends(verify_admin), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    db.query(Zone).filter(Zone.camera_id == camera_id).delete()
    db.query(AlertConfig).filter(AlertConfig.camera_id == camera_id).delete()
    db.delete(cam)
    db.commit()

    if camera_id in recorder.active_recorders:
        recorder.active_recorders[camera_id].stop()
        del recorder.active_recorders[camera_id]

    if camera_id in ai_worker.active_ai_workers:
        ai_worker.active_ai_workers[camera_id].stop()
        del ai_worker.active_ai_workers[camera_id]

    return {"message": "Camera removed successfully"}


@router.get("/{camera_id}/zones")
def get_camera_zones(camera_id: str, user=Depends(verify_viewer), db: Session = Depends(get_db)):
    zones = db.query(Zone).filter(Zone.camera_id == camera_id).all()
    return [
        {
            "id": z.id,
            "camera_id": z.camera_id,
            "type": z.type,
            "name": z.name,
            "points": json.loads(z.points),
            "direction_vector": json.loads(z.direction_vector) if z.direction_vector else None
        } for z in zones
    ]


@router.post("/{camera_id}/zones")
def save_camera_zones(camera_id: str, zones: list = Body(...), user=Depends(verify_admin), db: Session = Depends(get_db)):
    db.query(Zone).filter(Zone.camera_id == camera_id).delete()

    for z in zones:
        points_data = z.get("points", [])
        dir_vec = z.get("direction_vector", None)

        new_zone = Zone(
            camera_id=camera_id,
            type=z.get("type", "restricted"),
            name=z.get("name", "Zone"),
            points=json.dumps(points_data),
            direction_vector=json.dumps(dir_vec) if dir_vec else None
        )
        db.add(new_zone)

    db.commit()
    return {"message": "Camera zones saved successfully"}


@router.get("/{camera_id}/stream")
def get_camera_resolved_stream(camera_id: str, request: Request, user=Depends(verify_viewer), db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    original_url = cam.stream_url

    if os.path.exists(original_url) or original_url.lower().endswith((".avi", ".mp4", ".mkv", ".mov")):
        base_url = str(request.base_url).rstrip("/")
        mjpeg_url = f"{base_url}/api/v1/cameras/{camera_id}/mjpeg"
        return {"stream_url": mjpeg_url, "is_hls": False}

    resolved = resolve_stream_url(camera_id, original_url)

    if not resolved:
        return {"stream_url": original_url, "is_hls": False}

    if is_youtube_url(original_url) and resolved != original_url:
        base_url = str(request.base_url).rstrip("/")
        proxied_url = f"{base_url}/api/v1/proxy/m3u8?url={urllib.parse.quote_plus(resolved)}"
        return {"stream_url": proxied_url, "is_hls": True}

    if resolved.startswith("rtsp://127.0.0.1:8554/") or resolved.startswith("rtsp://localhost:8554/"):
        cam_id = resolved.split("/")[-1]
        hls_url = f"http://localhost:8888/{cam_id}/index.m3u8"
        return {"stream_url": hls_url, "is_hls": True}

    return {"stream_url": resolved, "is_hls": False}


import asyncio

@router.get("/{camera_id}/mjpeg")
async def stream_camera_mjpeg(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    stream = stream_manager.get_stream(camera_id, cam.stream_url)
    loop = asyncio.get_running_loop()

    async def generate():
        last_ts = 0.0
        while True:
            success, frame, ts = await loop.run_in_executor(None, stream.get_frame, last_ts)
            if success and frame is not None:
                last_ts = ts
                ret, buffer = await loop.run_in_executor(
                    None, lambda: cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                )
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            await asyncio.sleep(0.04)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
