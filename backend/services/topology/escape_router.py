"""
Predictive Next-Hop Escape Routing Engine (Prompt 1.3)
=====================================================
Calculates downstream camera interception points and arrival time windows (ETAs)
for fleeing targets departing from a known surveillance camera waypoint.
Uses camera topological graph traversal and calibrated velocity bounds with zero new GPU load.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from ...database.models import Camera, CameraEdge, CameraNode, _istnow

logger = logging.getLogger(__name__)


def predict_next_hop_escape_routes(
    db: Session,
    source_camera_identifier: str,
    target_description: str = "Vehicle",
    heading_direction: Optional[str] = "north",
    departure_time: Optional[datetime.datetime] = None,
    observed_speed_kmh: float = 40.0,
    max_hops: int = 2,
) -> Dict[str, Any]:
    """
    Computes predicted next-hop interception points based on camera graph edges,
    directional headings, and estimated transit times.
    """
    if departure_time is None:
        departure_time = _istnow()

    all_cameras = db.query(Camera).all()
    cam_by_id = {c.id.lower(): c for c in all_cameras}
    cam_by_name = {c.name.lower(): c for c in all_cameras if c.name}

    # Resolve source camera
    src_clean = source_camera_identifier.strip().lower()
    source_cam = None
    if src_clean in cam_by_id:
        source_cam = cam_by_id[src_clean]
    elif src_clean in cam_by_name:
        source_cam = cam_by_name[src_clean]
    else:
        # Partial match
        for name, c in cam_by_name.items():
            if src_clean in name or name in src_clean:
                source_cam = c
                break
        if not source_cam:
            for cid, c in cam_by_id.items():
                if src_clean in cid:
                    source_cam = c
                    break

    if not source_cam:
        # Fallback to first active camera if not found
        source_cam = all_cameras[0] if all_cameras else None

    if not source_cam:
        return {
            "success": False,
            "error": f"Source camera '{source_camera_identifier}' not found in network.",
            "routes": [],
        }

    src_id = source_cam.id
    src_name = source_cam.name or src_id
    heading_clean = (heading_direction or "forward").lower()

    # 1. Fetch direct active edges from source camera
    edges = db.query(CameraEdge).filter(
        CameraEdge.source_camera_id == src_id,
        CameraEdge.is_active == True,
    ).all()

    # If no explicit edges exist for this node:
    total_network_edges = db.query(CameraEdge).filter(CameraEdge.is_active == True).count()
    if not edges:
        if total_network_edges > 0:
            # Topology is configured and this node is a terminal boundary / dead-end
            return {
                "success": True,
                "source_camera": {
                    "id": source_cam.id,
                    "name": src_name,
                    "location": source_cam.location or "Terminal Waypoint",
                },
                "target_description": target_description,
                "heading_direction": heading_clean.capitalize(),
                "departure_time": departure_time.strftime("%H:%M:%S"),
                "observed_speed_kmh": observed_speed_kmh,
                "predicted_next_hops_count": 0,
                "routes": [],
                "is_dead_end": True,
                "message": f"Camera '{src_name}' is a terminal boundary checkpoint with no outgoing transit routes."
            }
        else:
            # Uninitialized network fallback
            edges = _generate_spatial_neighborhood_edges(db, source_cam, all_cameras)

    routes = []
    # Convert speed from km/h to m/s
    speed_ms = max(5.0, (observed_speed_kmh * 1000.0) / 3600.0)

    heading_clean = (heading_direction or "forward").lower()

    for edge in edges:
        target_cam = cam_by_id.get(edge.target_camera_id.lower())
        if not target_cam:
            continue

        tgt_name = target_cam.name or target_cam.id
        dist_m = edge.distance_meters or 500.0

        # Calculate transit seconds based on speed and edge boundaries
        nominal_transit_sec = dist_m / speed_ms
        transit_min_sec = int(max(15, nominal_transit_sec * 0.75))
        transit_max_sec = int(max(transit_min_sec + 20, nominal_transit_sec * 1.35))

        # Check directional alignment
        allowed = []
        try:
            allowed = json.loads(edge.allowed_directions or "[]")
        except Exception:
            allowed = ["forward", heading_clean]

        direction_match = any(
            heading_clean in d.lower() or d.lower() in heading_clean or d.lower() == "forward"
            for d in allowed
        )
        
        # Probability calculation based on heading alignment and distance
        probability = 0.85 if direction_match else 0.45
        if "north" in heading_clean and "north" in tgt_name.lower():
            probability = 0.95
        elif "south" in heading_clean and "south" in tgt_name.lower():
            probability = 0.95
        elif "east" in heading_clean and "east" in tgt_name.lower():
            probability = 0.95
        elif "west" in heading_clean and "west" in tgt_name.lower():
            probability = 0.95

        eta_start = departure_time + datetime.timedelta(seconds=transit_min_sec)
        eta_end = departure_time + datetime.timedelta(seconds=transit_max_sec)

        routes.append({
            "hop": 1,
            "camera_id": target_cam.id,
            "camera_name": tgt_name,
            "location": target_cam.location or "Junction Checkpoint",
            "distance_meters": round(dist_m, 1),
            "estimated_transit_seconds": f"{transit_min_sec}s - {transit_max_sec}s",
            "eta_window_start": eta_start.strftime("%H:%M:%S"),
            "eta_window_end": eta_end.strftime("%H:%M:%S"),
            "eta_display": f"{eta_start.strftime('%H:%M:%S')} - {eta_end.strftime('%H:%M:%S')}",
            "intercept_probability": round(probability, 2),
            "priority": "HIGH" if probability >= 0.75 else "MEDIUM",
            "recommended_action": f"Alert operator to monitor {tgt_name} feed ({target_cam.location or 'Downstream Junction'})"
        })

    # Sort routes by intercept probability descending, then distance
    routes.sort(key=lambda r: (-r["intercept_probability"], r["distance_meters"]))

    return {
        "success": True,
        "source_camera": {
            "id": source_cam.id,
            "name": src_name,
            "location": source_cam.location or "Starting Waypoint",
        },
        "target_description": target_description,
        "heading_direction": heading_clean.capitalize(),
        "departure_time": departure_time.strftime("%H:%M:%S"),
        "observed_speed_kmh": observed_speed_kmh,
        "predicted_next_hops_count": len(routes),
        "routes": routes,
    }


def _generate_spatial_neighborhood_edges(
    db: Session,
    source_cam: Camera,
    all_cameras: List[Camera],
) -> List[CameraEdge]:
    """Fallback generator that connects adjacent camera nodes based on list sequence or geometry."""
    edges = []
    other_cams = [c for c in all_cameras if c.id != source_cam.id]
    for idx, c in enumerate(other_cams[:3]):
        dist = 450.0 + (idx * 200.0)
        edges.append(CameraEdge(
            source_camera_id=source_cam.id,
            target_camera_id=c.id,
            distance_meters=dist,
            expected_transit_sec_min=int(dist / 15.0),
            expected_transit_sec_max=int(dist / 8.0),
            allowed_directions=json.dumps(["forward", "north", "south", "east", "west"]),
            is_active=True,
        ))
    return edges
