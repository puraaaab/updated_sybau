import os
import json
import uuid
import datetime
from typing import Optional, List, Dict, Any, Tuple, Set
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..database.models import Track, Camera, UnifiedSighting, CoOccurrenceCluster
from ..auth.helpers import verify_viewer, verify_operator

router = APIRouter(prefix="/forensics", tags=["CoOccurrence"])

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
def _istnow(): return datetime.datetime.now(_IST)


class ClusterReviewRequest(BaseModel):
    new_status: str  # "CONFIRMED_CONVOY" or "DISMISSED_FALSE_POSITIVE"
    review_notes: Optional[str] = None


class RunAnalysisRequest(BaseModel):
    time_window_minutes: Optional[int] = 15
    min_sightings: Optional[int] = 3
    min_cameras: Optional[int] = 2


@router.get("/co-occurrence")
def get_suspect_co_occurrence(
    camera_id: str = Query(default=None),
    time_window_minutes: int = Query(default=5),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """
    Spatial-Temporal Co-Occurrence Graph Analysis (Single Camera / Local Window).
    """
    query = db.query(Track)
    if camera_id:
        query = query.filter(Track.camera_id == camera_id)
        
    recent_tracks = query.order_by(Track.first_seen.desc()).limit(30).all()
    cams_dict = {c.id: c for c in db.query(Camera).all()}
    
    groups = []
    processed_ids = set()
    
    for i, t1 in enumerate(recent_tracks):
        if t1.id in processed_ids:
            continue
            
        group_members = [t1]
        processed_ids.add(t1.id)
        
        for t2 in recent_tracks[i + 1:]:
            if t2.id in processed_ids:
                continue
                
            same_cam = (t1.camera_id == t2.camera_id)
            time_diff = abs((t1.first_seen - t2.first_seen).total_seconds()) if (t1.first_seen and t2.first_seen) else 0
            
            if same_cam and time_diff <= (time_window_minutes * 60):
                group_members.append(t2)
                processed_ids.add(t2.id)
                
        if len(group_members) >= 2:
            cam = cams_dict.get(t1.camera_id)
            groups.append({
                "group_id": f"GROUP_{t1.camera_id}_{t1.id}",
                "camera_id": t1.camera_id,
                "camera_name": cam.name if cam else t1.camera_id,
                "location": cam.location if cam else "Main Area",
                "timestamp": t1.first_seen.isoformat() if t1.first_seen else _istnow().isoformat(),
                "confidence_score": min(round(0.80 + (len(group_members) * 0.03), 2), 0.99),
                "member_count": len(group_members),
                "members": [
                    {
                        "track_uuid": m.track_uuid,
                        "label": m.label,
                        "speed": round(m.speed, 1),
                        "first_seen": m.first_seen.strftime("%H:%M:%S") if m.first_seen else "N/A"
                    }
                    for m in group_members
                ],
                "analytical_summary": f"Spatial-Temporal Link: {len(group_members)} entities detected co-occurring at {cam.name if cam else t1.camera_id} within {time_window_minutes} min window."
            })

    return {
        "time_window_minutes": time_window_minutes,
        "groups_found": len(groups),
        "co_occurrence_groups": groups
    }


@router.post("/co-occurrence/analyze")
def run_convoy_co_occurrence_analysis(
    payload: Optional[RunAnalysisRequest] = None,
    user=Depends(verify_operator),
    db: Session = Depends(get_db)
):
    """
    Module 5: Multi-Camera Spatio-Temporal Convoy / Accomplice Detection.
    Clusters sightings where target pairs travel together (Delta T <= 3s) across >= 2 cameras and >= 3 sightings.
    ALWAYS defaults status to FLAGGED_PENDING_REVIEW (never auto-confirmed).
    """
    win_min = payload.time_window_minutes if payload else 15
    min_sightings = payload.min_sightings if payload else 3
    min_cams = payload.min_cameras if payload else 2

    cutoff_time = _istnow() - datetime.timedelta(minutes=win_min)
    sightings = (
        db.query(UnifiedSighting)
        .filter(UnifiedSighting.timestamp >= cutoff_time)
        .order_by(UnifiedSighting.timestamp.asc())
        .all()
    )

    # Group sightings by camera_id and compare pairs within Delta T <= 3.0s (sliding window)
    cam_sightings = {}
    for s in sightings:
        if s.timestamp:
            cam_sightings.setdefault(s.camera_id, []).append(s)

    # Count co-occurrence pairs
    pair_stats = {}  # (t1_id, t2_id) -> { "cameras": set(), "sightings": int, "del_t_sum": float, "del_t_cnt": int, "t1_type": str, "t2_type": str }
    for cam_id, cam_list in cam_sightings.items():
        # Sort chronologically
        cam_list.sort(key=lambda x: x.timestamp)
        for i in range(len(cam_list)):
            s1 = cam_list[i]
            id1 = s1.license_plate or s1.track_uuid or f"sighting_{s1.id}"
            for j in range(i + 1, len(cam_list)):
                s2 = cam_list[j]
                delta_t = abs((s1.timestamp - s2.timestamp).total_seconds())
                if delta_t > 3.0:
                    break  # Chronological order ensures subsequent sightings are further away

                id2 = s2.license_plate or s2.track_uuid or f"sighting_{s2.id}"
                if id1 == id2:
                    continue

                pair_key = tuple(sorted([str(id1), str(id2)]))
                stats = pair_stats.setdefault(pair_key, {
                    "cameras": set(),
                    "sightings": 0,
                    "del_t_sum": 0.0,
                    "del_t_cnt": 0,
                    "t1_type": s1.primary_class,
                    "t2_type": s2.primary_class
                })
                stats["cameras"].add(cam_id)
                stats["sightings"] += 1
                stats["del_t_sum"] += delta_t
                stats["del_t_cnt"] += 1

    created_clusters = []
    for (p1, p2), stats in pair_stats.items():
        num_cams = len(stats["cameras"])
        num_sightings = stats["sightings"]

        if num_cams >= min_cams and num_sightings >= min_sightings:
            avg_dt = stats["del_t_sum"] / max(1, stats["del_t_cnt"])
            conf = min(0.99, round(0.70 + (0.08 * num_cams) + (0.04 * num_sightings) - (0.03 * avg_dt), 2))

            # Check if cluster already exists in DB
            existing = (
                db.query(CoOccurrenceCluster)
                .filter(
                    CoOccurrenceCluster.primary_target_id == p1,
                    CoOccurrenceCluster.companion_target_id == p2
                )
                .first()
            )
            if not existing:
                cluster_uid = f"convoy_{uuid.uuid4().hex[:10]}"
                cluster = CoOccurrenceCluster(
                    cluster_uuid=cluster_uid,
                    primary_target_id=p1,
                    companion_target_id=p2,
                    primary_type=stats["t1_type"],
                    companion_type=stats["t2_type"],
                    sightings_count=num_sightings,
                    cameras_count=num_cams,
                    cameras_involved_json=json.dumps(list(stats["cameras"])),
                    avg_time_delta_sec=round(avg_dt, 2),
                    confidence_score=conf,
                    status="FLAGGED_PENDING_REVIEW"  # CRITICAL: Always pending human review
                )
                db.add(cluster)
                created_clusters.append(cluster)
            else:
                existing.sightings_count = num_sightings
                existing.cameras_count = num_cams
                existing.cameras_involved_json = json.dumps(list(stats["cameras"]))
                existing.avg_time_delta_sec = round(avg_dt, 2)
                existing.confidence_score = conf

    db.commit()

    return {
        "success": True,
        "analyzed_time_window_minutes": win_min,
        "new_clusters_flagged": len(created_clusters),
        "total_co_occurrence_pairs_evaluated": len(pair_stats)
    }


@router.get("/co-occurrence/clusters")
def list_co_occurrence_clusters(
    status: Optional[str] = Query(default=None),
    user=Depends(verify_viewer),
    db: Session = Depends(get_db)
):
    """Lists all detected convoy & accomplice candidate clusters with their review status."""
    query = db.query(CoOccurrenceCluster)
    if status:
        query = query.filter(CoOccurrenceCluster.status == status)

    clusters = query.order_by(CoOccurrenceCluster.confidence_score.desc(), CoOccurrenceCluster.created_at.desc()).all()

    return {
        "count": len(clusters),
        "clusters": [
            {
                "id": c.id,
                "cluster_uuid": c.cluster_uuid,
                "primary_target_id": c.primary_target_id,
                "companion_target_id": c.companion_target_id,
                "primary_type": c.primary_type,
                "companion_type": c.companion_type,
                "sightings_count": c.sightings_count,
                "cameras_count": c.cameras_count,
                "cameras_involved": json.loads(c.cameras_involved_json or "[]"),
                "avg_time_delta_sec": c.avg_time_delta_sec,
                "confidence_score": c.confidence_score,
                "status": c.status,
                "reviewed_by": c.reviewed_by,
                "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
                "review_notes": c.review_notes,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in clusters
        ]
    }


@router.post("/co-occurrence/clusters/{cluster_uuid}/review")
def review_co_occurrence_cluster(
    cluster_uuid: str,
    payload: ClusterReviewRequest,
    user=Depends(verify_operator),
    db: Session = Depends(get_db)
):
    """
    Human Investigator Review Workflow.
    Transitions status from FLAGGED_PENDING_REVIEW -> CONFIRMED_CONVOY or DISMISSED_FALSE_POSITIVE.
    """
    allowed_statuses = ["CONFIRMED_CONVOY", "DISMISSED_FALSE_POSITIVE"]
    if payload.new_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review status. Allowed values: {allowed_statuses}"
        )

    cluster = db.query(CoOccurrenceCluster).filter(CoOccurrenceCluster.cluster_uuid == cluster_uuid).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Co-occurrence cluster not found.")

    username = getattr(user, "username", None) or (user.get("username") if isinstance(user, dict) else "operator")

    cluster.status = payload.new_status
    cluster.reviewed_by = username
    cluster.reviewed_at = _istnow()
    cluster.review_notes = payload.review_notes or ""

    db.commit()

    return {
        "success": True,
        "cluster_uuid": cluster.cluster_uuid,
        "new_status": cluster.status,
        "reviewed_by": cluster.reviewed_by,
        "reviewed_at": cluster.reviewed_at.isoformat()
    }


def find_convoy_companions(
    db: Session,
    target_identifier: str,
    time_window_minutes: int = 60,
    max_gap_seconds: float = 45.0,
    min_cameras: int = 2,
) -> Dict[str, Any]:
    """
    Prompt 6.1: Convoy & Shadow-Vehicle Co-Occurrence Detection.
    Identifies vehicles traveling in close temporal proximity (gap <= max_gap_seconds)
    to a target across >= min_cameras separate camera checkpoints.
    """
    from ..database.models import VehicleJourneyEvent, Vehicle, RawOCR

    clean_target = target_identifier.strip().upper()
    cutoff = _istnow() - datetime.timedelta(minutes=time_window_minutes)

    # 1. Fetch all sightings of target vehicle
    target_sightings = (
        db.query(VehicleJourneyEvent)
        .filter(VehicleJourneyEvent.timestamp_start >= cutoff)
        .filter(
            (VehicleJourneyEvent.license_plate.ilike(f"%{clean_target}%"))
            | (VehicleJourneyEvent.track_id.ilike(f"%{clean_target}%"))
            | (VehicleJourneyEvent.global_vehicle_id.ilike(f"%{clean_target}%"))
        )
        .order_by(VehicleJourneyEvent.timestamp_start.asc())
        .all()
    )

    if not target_sightings:
        # Check if target is in RawOCR
        ocr_hits = (
            db.query(RawOCR)
            .filter(RawOCR.timestamp >= cutoff)
            .filter(RawOCR.raw_text.ilike(f"%{clean_target}%"))
            .all()
        )
        if not ocr_hits:
            return {
                "success": False,
                "target": clean_target,
                "convoys_detected_count": 0,
                "message": f"No sightings found for target '{clean_target}' within past {time_window_minutes} minutes.",
                "convoy_candidates": [],
            }

    # Extract target sighting checkpoints: (camera_id, timestamp, plate, snapshot)
    target_checkpoints = []
    for ts in target_sightings:
        target_checkpoints.append({
            "camera_id": ts.camera_id,
            "timestamp": ts.timestamp_start,
            "plate": ts.license_plate or clean_target,
            "snapshot_url": ts.snapshot_url,
        })

    cam_lookup = {c.id: c.name for c in db.query(Camera).all()}
    candidate_co_occurrences = {}  # companion_id -> list of shared sightings

    for cp in target_checkpoints:
        c_id = cp["camera_id"]
        t_center = cp["timestamp"]
        t_min = t_center - datetime.timedelta(seconds=max_gap_seconds)
        t_max = t_center + datetime.timedelta(seconds=max_gap_seconds)

        # Query all other vehicles seen at this camera around t_center
        nearby_vehs = (
            db.query(VehicleJourneyEvent)
            .filter(
                VehicleJourneyEvent.camera_id == c_id,
                VehicleJourneyEvent.timestamp_start >= t_min,
                VehicleJourneyEvent.timestamp_start <= t_max,
            )
            .all()
        )

        for nv in nearby_vehs:
            c_plate = (nv.license_plate or nv.track_id or nv.global_vehicle_id or "").strip().upper()
            if not c_plate or c_plate == clean_target or clean_target in c_plate:
                continue

            gap_sec = abs((nv.timestamp_start - t_center).total_seconds())
            if gap_sec > max_gap_seconds:
                continue

            candidate_co_occurrences.setdefault(c_plate, []).append({
                "camera_id": c_id,
                "camera_name": cam_lookup.get(c_id, c_id),
                "target_time": t_center.strftime("%H:%M:%S"),
                "companion_time": nv.timestamp_start.strftime("%H:%M:%S"),
                "trailing_gap_seconds": round(gap_sec, 1),
                "vehicle_type": getattr(nv, "vehicle_type", "vehicle") or "car",
                "snapshot_url": nv.snapshot_url or f"/api/v1/playback/snapshot/{c_id}_latest",
            })

    # Filter candidates with sightings at >= min_cameras
    convoy_results = []
    for companion_id, shared_events in candidate_co_occurrences.items():
        distinct_cams = set(e["camera_id"] for e in shared_events)
        if len(distinct_cams) >= min_cameras:
            avg_gap = sum(e["trailing_gap_seconds"] for e in shared_events) / len(shared_events)
            # Correlation score based on camera count and proximity tightness
            corr_score = min(0.99, round(0.65 + (0.10 * len(distinct_cams)) - (0.005 * avg_gap), 2))

            convoy_results.append({
                "companion_identifier": companion_id,
                "cameras_co_occurred_count": len(distinct_cams),
                "total_shared_sightings": len(shared_events),
                "avg_trailing_gap_seconds": round(avg_gap, 1),
                "correlation_confidence": corr_score,
                "threat_assessment": "SUSPECTED_SHADOW_ESCORT" if corr_score >= 0.80 else "HIGH_CORRELATION_CONVOY",
                "shared_timeline": shared_events,
            })

    convoy_results.sort(key=lambda x: -x["correlation_confidence"])

    return {
        "success": True,
        "target_identifier": clean_target,
        "time_window_minutes": time_window_minutes,
        "target_checkpoints_count": len(target_checkpoints),
        "convoys_detected_count": len(convoy_results),
        "convoy_candidates": convoy_results,
    }


def seed_demo_convoy_data(db: Session) -> Dict[str, Any]:
    """
    Seeds a realistic multi-camera convoy scenario for field evaluation:
    Target: White Scorpio (DL01AB1234)
    Shadow Escort: Black Fortuner (HR26DK9901) trailing by 8-12 seconds
    Across Cam 1 (Main Gate), Cam 2 (North Junction), and Cam 3 (Highway Exit).
    """
    from ..database.models import VehicleJourneyEvent

    now = _istnow()
    t1 = now - datetime.timedelta(minutes=18)
    t2 = now - datetime.timedelta(minutes=12)
    t3 = now - datetime.timedelta(minutes=5)

    cams = [c.id for c in db.query(Camera).all()]
    if len(cams) < 2:
        cams = ["cam_1", "cam_2", "cam_3"]

    c1 = cams[0]
    c2 = cams[1] if len(cams) > 1 else cams[0]
    c3 = cams[2] if len(cams) > 2 else c2

    # Remove previous demo runs
    db.query(VehicleJourneyEvent).filter(
        VehicleJourneyEvent.license_plate.in_(["DL01AB1234", "HR26DK9901", "UP16AX5555"])
    ).delete(synchronize_session=False)

    demo_events = [
        # Checkpoint 1: Gate
        VehicleJourneyEvent(
            global_vehicle_id="VEH_SCORPIO_DEMO",
            track_id=f"trk_scorpio_{uuid.uuid4().hex[:6]}",
            camera_id=c1,
            license_plate="DL01AB1234",
            timestamp_start=t1,
            timestamp_end=t1 + datetime.timedelta(seconds=4),
            snapshot_url=f"/api/v1/playback/snapshot/{c1}_scorpio",
            confidence=0.96,
        ),
        VehicleJourneyEvent(
            global_vehicle_id="VEH_FORTUNER_DEMO",
            track_id=f"trk_fortuner_{uuid.uuid4().hex[:6]}",
            camera_id=c1,
            license_plate="HR26DK9901",
            timestamp_start=t1 + datetime.timedelta(seconds=8),  # 8s gap
            timestamp_end=t1 + datetime.timedelta(seconds=12),
            snapshot_url=f"/api/v1/playback/snapshot/{c1}_fortuner",
            confidence=0.94,
        ),
        # Checkpoint 2: North Junction
        VehicleJourneyEvent(
            global_vehicle_id="VEH_SCORPIO_DEMO",
            track_id=f"trk_scorpio_{uuid.uuid4().hex[:6]}",
            camera_id=c2,
            license_plate="DL01AB1234",
            timestamp_start=t2,
            timestamp_end=t2 + datetime.timedelta(seconds=5),
            snapshot_url=f"/api/v1/playback/snapshot/{c2}_scorpio",
            confidence=0.97,
        ),
        VehicleJourneyEvent(
            global_vehicle_id="VEH_FORTUNER_DEMO",
            track_id=f"trk_fortuner_{uuid.uuid4().hex[:6]}",
            camera_id=c2,
            license_plate="HR26DK9901",
            timestamp_start=t2 + datetime.timedelta(seconds=11),  # 11s gap
            timestamp_end=t2 + datetime.timedelta(seconds=16),
            snapshot_url=f"/api/v1/playback/snapshot/{c2}_fortuner",
            confidence=0.95,
        ),
        # Checkpoint 3: Highway Exit
        VehicleJourneyEvent(
            global_vehicle_id="VEH_SCORPIO_DEMO",
            track_id=f"trk_scorpio_{uuid.uuid4().hex[:6]}",
            camera_id=c3,
            license_plate="DL01AB1234",
            timestamp_start=t3,
            timestamp_end=t3 + datetime.timedelta(seconds=4),
            snapshot_url=f"/api/v1/playback/snapshot/{c3}_scorpio",
            confidence=0.98,
        ),
        VehicleJourneyEvent(
            global_vehicle_id="VEH_FORTUNER_DEMO",
            track_id=f"trk_fortuner_{uuid.uuid4().hex[:6]}",
            camera_id=c3,
            license_plate="HR26DK9901",
            timestamp_start=t3 + datetime.timedelta(seconds=9),  # 9s gap
            timestamp_end=t3 + datetime.timedelta(seconds=13),
            snapshot_url=f"/api/v1/playback/snapshot/{c3}_fortuner",
            confidence=0.96,
        ),
    ]

    db.add_all(demo_events)
    db.commit()

    return {
        "success": True,
        "message": "Seeded 3-checkpoint convoy events for target DL01AB1234 and shadow vehicle HR26DK9901.",
        "target": "DL01AB1234",
        "companion": "HR26DK9901",
        "checkpoints": [c1, c2, c3],
    }


@router.get("/convoy/query")
def query_convoy_companions(
    target_id: str = Query(..., description="Target vehicle license plate or track UUID"),
    time_window_minutes: int = Query(default=60),
    max_gap_seconds: float = Query(default=45.0),
    min_cameras: int = Query(default=2),
    db: Session = Depends(get_db),
    user=Depends(verify_viewer),
):
    """API endpoint to query convoy / companion vehicles for any target."""
    return find_convoy_companions(
        db=db,
        target_identifier=target_id,
        time_window_minutes=time_window_minutes,
        max_gap_seconds=max_gap_seconds,
        min_cameras=min_cameras,
    )


@router.post("/convoy/seed-demo")
def seed_demo_convoy(
    db: Session = Depends(get_db),
    user=Depends(verify_operator),
):
    """Seeds multi-camera convoy events for testing Prompt 6.1."""
    return seed_demo_convoy_data(db)
