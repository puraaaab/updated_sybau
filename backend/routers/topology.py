import json
import logging
import math
import uuid
import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database.connection import SessionLocal
from ..database.models import Camera, CameraNode, CameraEdge
from ..auth.helpers import verify_viewer, verify_operator
from ..messaging.kafka_client import event_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/topology", tags=["Camera Topology & Predictive Routing"])

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
def _istnow(): return datetime.datetime.now(_IST)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class NodePositionUpdate(BaseModel):
    map_x: float
    map_y: float
    zone_group: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lng: Optional[float] = None


class EdgeCreateRequest(BaseModel):
    source_camera_id: str
    target_camera_id: str
    distance_meters: Optional[float] = 500.0
    expected_transit_sec_min: Optional[int] = 60
    expected_transit_sec_max: Optional[int] = 300
    allowed_directions: Optional[List[str]] = ["forward"]


class PredictiveAlertRequest(BaseModel):
    source_camera_id: str
    target_identifier: str  # e.g. "KA51MB8811" or "TRK_cam_7_12"
    target_type: str        # e.g. "vehicle" or "person"
    heading_direction: Optional[str] = "forward"
    observed_speed_kmh: Optional[float] = 40.0


@router.get("")
def get_topology_graph(db: Session = Depends(get_db), user=Depends(verify_viewer)):
    """Fetches the full camera topological graph (nodes + directed edges)."""
    # 1. Sync any new cameras into camera_nodes if missing
    all_cameras = db.query(Camera).all()
    existing_nodes = {n.camera_id: n for n in db.query(CameraNode).all()}

    num_cams = max(1, len(all_cameras))
    center_x, center_y, radius = 500.0, 350.0, 240.0

    new_nodes = []
    for idx, cam in enumerate(all_cameras):
        if cam.id not in existing_nodes:
            angle = (2 * math.pi * idx) / num_cams
            calc_x = round(center_x + radius * math.cos(angle), 1)
            calc_y = round(center_y + radius * math.sin(angle), 1)
            node = CameraNode(
                camera_id=cam.id,
                label=cam.name or cam.id,
                geo_lat=cam.latitude,
                geo_lng=cam.longitude,
                map_x=calc_x,
                map_y=calc_y,
                zone_group="Main City",
                is_active=True
            )
            db.add(node)
            new_nodes.append(node)

    if new_nodes:
        db.commit()

    nodes = db.query(CameraNode).all()
    edges = db.query(CameraEdge).filter(CameraEdge.is_active == True).all()

    # Seed default sequential edges if zero edges exist
    if not edges and len(nodes) >= 2:
        for i in range(len(nodes) - 1):
            db.add(CameraEdge(
                source_camera_id=nodes[i].camera_id,
                target_camera_id=nodes[i+1].camera_id,
                distance_meters=600.0,
                expected_transit_sec_min=45,
                expected_transit_sec_max=180,
                allowed_directions=json.dumps(["forward"])
            ))
        db.commit()
        edges = db.query(CameraEdge).filter(CameraEdge.is_active == True).all()

    return {
        "nodes": [
            {
                "camera_id": n.camera_id,
                "label": n.label,
                "geo_lat": n.geo_lat,
                "geo_lng": n.geo_lng,
                "map_x": n.map_x,
                "map_y": n.map_y,
                "zone_group": n.zone_group,
                "is_active": n.is_active,
                "updated_at": n.updated_at.isoformat() if n.updated_at else ""
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source_camera_id,
                "target": e.target_camera_id,
                "distance_meters": e.distance_meters,
                "expected_transit_sec_min": e.expected_transit_sec_min,
                "expected_transit_sec_max": e.expected_transit_sec_max,
                "allowed_directions": json.loads(e.allowed_directions or "[]"),
                "is_active": e.is_active
            }
            for e in edges
        ]
    }


@router.put("/nodes/{camera_id}")
def update_node_position(
    camera_id: str,
    payload: NodePositionUpdate,
    db: Session = Depends(get_db),
    user=Depends(verify_operator)
):
    """Debounced persistence of user-dragged camera node coordinates."""
    node = db.query(CameraNode).filter(CameraNode.camera_id == camera_id).first()
    if not node:
        # Create node if not yet exists
        cam = db.query(Camera).filter(Camera.id == camera_id).first()
        label_str = cam.name if cam else camera_id
        node = CameraNode(
            camera_id=camera_id,
            label=label_str,
            map_x=payload.map_x,
            map_y=payload.map_y,
            zone_group=payload.zone_group or "Main City"
        )
        db.add(node)
    else:
        node.map_x = payload.map_x
        node.map_y = payload.map_y
        if payload.zone_group is not None:
            node.zone_group = payload.zone_group
        if payload.geo_lat is not None:
            node.geo_lat = payload.geo_lat
        if payload.geo_lng is not None:
            node.geo_lng = payload.geo_lng
        node.updated_at = _istnow()

    db.commit()
    return {
        "success": True,
        "camera_id": camera_id,
        "map_x": node.map_x,
        "map_y": node.map_y,
        "updated_at": node.updated_at.isoformat() if node.updated_at else ""
    }


@router.post("/edges")
def create_or_update_edge(
    payload: EdgeCreateRequest,
    db: Session = Depends(get_db),
    user=Depends(verify_operator)
):
    """Adds or updates a directed transit edge between camera nodes."""
    if payload.source_camera_id == payload.target_camera_id:
        raise HTTPException(status_code=400, detail="Cannot create self-loop edge on the same camera.")

    edge = (
        db.query(CameraEdge)
        .filter(
            CameraEdge.source_camera_id == payload.source_camera_id,
            CameraEdge.target_camera_id == payload.target_camera_id
        )
        .first()
    )
    if not edge:
        edge = CameraEdge(
            source_camera_id=payload.source_camera_id,
            target_camera_id=payload.target_camera_id,
            distance_meters=payload.distance_meters or 500.0,
            expected_transit_sec_min=payload.expected_transit_sec_min or 60,
            expected_transit_sec_max=payload.expected_transit_sec_max or 300,
            allowed_directions=json.dumps(payload.allowed_directions or ["forward"]),
            is_active=True
        )
        db.add(edge)
    else:
        edge.distance_meters = payload.distance_meters or edge.distance_meters
        edge.expected_transit_sec_min = payload.expected_transit_sec_min or edge.expected_transit_sec_min
        edge.expected_transit_sec_max = payload.expected_transit_sec_max or edge.expected_transit_sec_max
        if payload.allowed_directions is not None:
            edge.allowed_directions = json.dumps(payload.allowed_directions)
        edge.is_active = True

    db.commit()
    return {
        "success": True,
        "edge_id": edge.id,
        "source": edge.source_camera_id,
        "target": edge.target_camera_id,
        "distance_meters": edge.distance_meters,
        "transit_window_sec": [edge.expected_transit_sec_min, edge.expected_transit_sec_max]
    }


@router.delete("/edges/{edge_id}")
def delete_edge(edge_id: int, db: Session = Depends(get_db), user=Depends(verify_operator)):
    """Deletes a topological edge."""
    db.query(CameraEdge).filter(CameraEdge.id == edge_id).delete()
    db.commit()
    return {"success": True, "edge_id": edge_id}


@router.post("/reset-layout")
def reset_canonical_layout(db: Session = Depends(get_db), user=Depends(verify_operator)):
    """Resets all node positions to a canonical circular layout without deleting any edge data."""
    nodes = db.query(CameraNode).all()
    num_nodes = max(1, len(nodes))
    center_x, center_y, radius = 500.0, 350.0, 240.0

    for idx, node in enumerate(nodes):
        angle = (2 * math.pi * idx) / num_nodes
        node.map_x = round(center_x + radius * math.cos(angle), 1)
        node.map_y = round(center_y + radius * math.sin(angle), 1)
        node.updated_at = _istnow()

    db.commit()
    return {"success": True, "message": "Topological layout reset to canonical geometry. Edge transit rules preserved."}


@router.post("/predict")
def trigger_predictive_transit_alert(
    payload: PredictiveAlertRequest,
    db: Session = Depends(get_db),
    user=Depends(verify_operator)
):
    """Evaluates target exit from Cam A and calculates expected arrival window at downstream Cam B."""
    downstream_edges = (
        db.query(CameraEdge)
        .filter(CameraEdge.source_camera_id == payload.source_camera_id, CameraEdge.is_active == True)
        .all()
    )

    if not downstream_edges:
        return {
            "predicted": False,
            "message": f"No downstream topological routes configured for {payload.source_camera_id}."
        }

    now = _istnow()
    alerts_generated = []

    cam_lookup = {c.id: c.name for c in db.query(Camera).all()}
    source_name = cam_lookup.get(payload.source_camera_id, payload.source_camera_id)

    for edge in downstream_edges:
        target_name = cam_lookup.get(edge.target_camera_id, edge.target_camera_id)
        window_start = now + datetime.timedelta(seconds=edge.expected_transit_sec_min)
        window_end = now + datetime.timedelta(seconds=edge.expected_transit_sec_max)

        alert_msg = (
            f"📡 PREDICTIVE TRANSIT ALERT: Target '{payload.target_identifier}' ({payload.target_type}) "
            f"departed {source_name}. Expected at {target_name} between "
            f"{window_start.strftime('%H:%M:%S')} and {window_end.strftime('%H:%M:%S')}."
        )

        alert_payload = {
            "type": "PREDICTIVE_TRANSIT",
            "source_camera_id": payload.source_camera_id,
            "target_camera_id": edge.target_camera_id,
            "target_identifier": payload.target_identifier,
            "target_type": payload.target_type,
            "distance_meters": edge.distance_meters,
            "expected_window_start": window_start.isoformat(),
            "expected_window_end": window_end.isoformat(),
            "message": alert_msg,
            "timestamp": now.isoformat()
        }

        # Broadcast via Kafka/MemoryEventBus
        try:
            event_client.publish_alert(alert_payload)
        except Exception as k_err:
            logger.debug("[TopologyRouter] Kafka broadcast note: %s", k_err)

        alerts_generated.append(alert_payload)

    return {
        "predicted": True,
        "alerts_count": len(alerts_generated),
        "alerts": alerts_generated
    }
