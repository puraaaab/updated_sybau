"""
Live Watchlist & Hot-List Matching Engine
==========================================
Continuously checks incoming OCR license plates and face embeddings against
the Stolen Vehicle Hot-List and Wanted Persons Watchlists.
Dispatches immediate Canonical Alerts to Control Room.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from ...database.models import (
    Alert, CanonicalEvent, PersonWatchlist, StolenVehicleWatchlist, _istnow,
)
from ..integrations.cctns_service import lookup_cctns_person, lookup_cctns_vehicle

logger = logging.getLogger(__name__)


def clean_plate(plate: str) -> str:
    """Normalize license plate to alphanumeric uppercase."""
    return re.sub(r"[^A-Za-z0-9]", "", plate).upper()


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def check_plate_against_stolen_watchlist(
    db: Session,
    raw_plate: str,
    camera_id: str,
    snapshot_url: Optional[str] = None,
    vehicle_type: str = "vehicle",
) -> Optional[Dict[str, Any]]:
    """
    Checks license plate against active stolen vehicles watchlist & CCTNS repository.
    If matched, creates an immutable Hot-List Alert and returns the match dossier.
    """
    cleaned = clean_plate(raw_plate)
    if len(cleaned) < 4:
        return None

    # 1. Check local DB watchlist
    matched_entry = (
        db.query(StolenVehicleWatchlist)
        .filter(StolenVehicleWatchlist.status == "ACTIVE")
        .filter(
            (StolenVehicleWatchlist.plate_number == cleaned)
            | (StolenVehicleWatchlist.plate_number.like(f"%{cleaned}%"))
        )
        .first()
    )

    # 2. Check CCTNS State Hot-List
    cctns_record = lookup_cctns_vehicle(cleaned)

    if not matched_entry and not cctns_record:
        return None

    # Construct alert payload
    plate_number = matched_entry.plate_number if matched_entry else cctns_record["plate_number"]
    fir_number = matched_entry.fir_number if matched_entry else cctns_record["fir_number"]
    police_station = matched_entry.police_station if matched_entry else cctns_record["police_station"]
    owner_name = matched_entry.owner_name if matched_entry else cctns_record["owner_name"]
    model = matched_entry.vehicle_make_model if matched_entry else cctns_record["vehicle_make_model"]

    event_uuid = f"hotlist_veh_{uuid.uuid4().hex[:12]}"
    dedup_key = f"hotlist_{cleaned}_{camera_id}_{_istnow().strftime('%Y%m%d%H%M')}"

    # Verify deduplication key to prevent alert spamming within same minute
    existing_event = db.query(CanonicalEvent).filter(CanonicalEvent.deduplication_key == dedup_key).first()
    if existing_event:
        return {
            "matched": True,
            "plate_number": plate_number,
            "fir_number": fir_number,
            "owner_name": owner_name,
            "model": model,
            "event_uuid": existing_event.event_uuid,
        }

    alert_title = f"🚨 HOT-LIST STOLEN VEHICLE: {plate_number}"
    alert_desc = (
        f"Stolen vehicle [{model} - {plate_number}] detected on camera {camera_id}. "
        f"Registered FIR: {fir_number} ({police_station}). Owner: {owner_name}."
    )

    canonical_event = CanonicalEvent(
        event_uuid=event_uuid,
        deduplication_key=dedup_key,
        camera_id=camera_id,
        event_type="stolen_vehicle_detected",
        source_type="anpr_watchlist",
        severity="critical",
        confidence=0.99,
        status="DETECTED",
    )
    db.add(canonical_event)

    legacy_alert = Alert(
        event_type="stolen_vehicle_detected",
        camera_id=camera_id,
        severity="CRITICAL",
        description=alert_desc,
        snapshot_url=snapshot_url,
        status="active",
        timestamp=_istnow(),
    )
    db.add(legacy_alert)

    try:
        db.commit()
        logger.warning(f"🚨 HOT-LIST VEHICLE ALERT FIRED: {plate_number} on {camera_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error persisting hot-list vehicle alert: {e}")

    return {
        "matched": True,
        "plate_number": plate_number,
        "fir_number": fir_number,
        "police_station": police_station,
        "owner_name": owner_name,
        "model": model,
        "cctns_details": cctns_record,
        "event_uuid": event_uuid,
    }


def check_face_against_person_watchlist(
    db: Session,
    face_embedding: List[float],
    camera_id: str,
    snapshot_url: Optional[str] = None,
    threshold: float = 0.75,
) -> Optional[Dict[str, Any]]:
    """
    Checks a 512-D ArcFace face vector against active wanted/missing persons watchlist.
    If similarity >= threshold, fires an immediate Watchlist Hit alert.
    """
    if not face_embedding or len(face_embedding) < 128:
        return None

    watchlist_persons = db.query(PersonWatchlist).filter(PersonWatchlist.status == "ACTIVE").all()
    if not watchlist_persons:
        return None

    best_match: Optional[PersonWatchlist] = None
    best_score: float = 0.0

    for person in watchlist_persons:
        try:
            target_vec = json.loads(person.face_embedding_json)
            if not target_vec or len(target_vec) != len(face_embedding):
                continue
            sim = cosine_similarity(face_embedding, target_vec)
            if sim > best_score:
                best_score = sim
                best_match = person
        except Exception:
            continue

    if not best_match or best_score < threshold:
        return None

    event_uuid = f"watchlist_face_{uuid.uuid4().hex[:12]}"
    dedup_key = f"watchlist_person_{best_match.person_uuid}_{camera_id}_{_istnow().strftime('%Y%m%d%H%M')}"

    existing_event = db.query(CanonicalEvent).filter(CanonicalEvent.deduplication_key == dedup_key).first()
    if existing_event:
        return {
            "matched": True,
            "person_name": best_match.full_name,
            "category": best_match.category,
            "case_reference": best_match.case_reference,
            "score": round(best_score, 3),
            "event_uuid": existing_event.event_uuid,
        }

    alert_title = f"🚨 WATCHLIST HIT: {best_match.full_name} ({best_match.category})"
    alert_desc = (
        f"Positive match for [{best_match.full_name}] (Score: {round(best_score * 100, 1)}%) "
        f"on camera {camera_id}. Category: {best_match.category}. Case: {best_match.case_reference}."
    )

    canonical_event = CanonicalEvent(
        event_uuid=event_uuid,
        deduplication_key=dedup_key,
        camera_id=camera_id,
        event_type="watchlist_person_detected",
        source_type="face_watchlist",
        severity="critical" if best_match.priority == "CRITICAL" else "high",
        confidence=best_score,
        status="DETECTED",
    )
    db.add(canonical_event)

    legacy_alert = Alert(
        event_type="watchlist_person_detected",
        camera_id=camera_id,
        severity="CRITICAL" if best_match.priority == "CRITICAL" else "HIGH",
        description=alert_desc,
        snapshot_url=snapshot_url,
        status="active",
        timestamp=_istnow(),
    )
    db.add(legacy_alert)

    try:
        db.commit()
        logger.warning(f"🚨 WATCHLIST FACE HIT FIRED: {best_match.full_name} on {camera_id} (Score: {best_score:.3f})")
    except Exception as e:
        db.rollback()
        logger.error(f"Error persisting watchlist face alert: {e}")

    # Fetch CCTNS dossier for enriched context
    cctns_data = lookup_cctns_person(best_match.full_name)

    return {
        "matched": True,
        "person_name": best_match.full_name,
        "alias": best_match.alias,
        "category": best_match.category,
        "case_reference": best_match.case_reference,
        "priority": best_match.priority,
        "score": round(best_score, 3),
        "cctns_dossier": cctns_data,
        "event_uuid": event_uuid,
    }
