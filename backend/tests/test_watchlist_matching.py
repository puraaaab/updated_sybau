"""
Unit tests for Stolen Vehicle Hot-List & Wanted Person Watchlist matching.
Verifies Prompts 3.4, 10.1, and 10.2 functionality and alert generation.
"""

import json
import pytest
from backend.database.connection import SessionLocal
from backend.database.models import (
    Alert, CanonicalEvent, PersonWatchlist, StolenVehicleWatchlist,
)
from backend.services.integrations.cctns_service import (
    lookup_cctns_person, lookup_cctns_vehicle, get_all_active_stolen_vehicles,
)
from backend.services.watchlist.matcher import (
    check_plate_against_stolen_watchlist,
    check_face_against_person_watchlist,
    clean_plate,
    cosine_similarity,
)


@pytest.fixture
def db_session():
    from backend.database.models import Base
    from backend.database.connection import engine
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_clean_plate():
    assert clean_plate("DL 01 AB 1234") == "DL01AB1234"
    assert clean_plate("hr-26-dk-9901") == "HR26DK9901"
    assert clean_plate("MH.02.CB.8492") == "MH02CB8492"


def test_cctns_mock_vehicle_lookup():
    # Known stolen car
    record = lookup_cctns_vehicle("DL-01-AB-1234")
    assert record is not None
    assert record["plate_number"] == "DL01AB1234"
    assert "Swift" in record["vehicle_make_model"]
    assert record["status"] == "WANTED_STOLEN"

    # Known hit and run
    record2 = lookup_cctns_vehicle("UP16Z1002")
    assert record2 is not None
    assert record2["fir_number"] == "FIR-120/2026/SEC-279"

    # Unknown clean plate
    clean_rec = lookup_cctns_vehicle("KA05MJ9999")
    assert clean_rec is None


def test_cctns_mock_person_lookup():
    # Wanted criminal
    record = lookup_cctns_person("Vikram Malhotra")
    assert record is not None
    assert record["cctns_id"] == "CCTNS-ND-2024-88912"
    assert "A_CLASS" in record["category"]
    assert record["threat_level"] == "EXTREME"

    # Missing child
    child = lookup_cctns_person("Aarav")
    assert child is not None
    assert child["category"] == "MISSING_CHILD"

    # Unknown person
    unknown = lookup_cctns_person("NonExistentPerson123")
    assert unknown is None


def test_stolen_vehicle_matching_and_alert_generation(db_session):
    # Seed a stolen vehicle in watchlist table
    test_plate = "DL01AB1234"
    existing = db_session.query(StolenVehicleWatchlist).filter_by(plate_number=test_plate).first()
    if not existing:
        veh = StolenVehicleWatchlist(
            plate_number=test_plate,
            vehicle_make_model="Maruti Swift Dzire",
            vehicle_color="White",
            fir_number="FIR-402/2026/SEC-379",
            police_station="Connaught Place PS",
            status="ACTIVE",
            priority="CRITICAL",
        )
        db_session.add(veh)
        db_session.commit()

    # Run matcher on OCR detection
    match_result = check_plate_against_stolen_watchlist(
        db=db_session,
        raw_plate="DL 01 AB 1234",
        camera_id="cam_01",
        snapshot_url="/snapshots/test_stolen.jpg",
    )

    assert match_result is not None
    assert match_result["matched"] is True
    assert match_result["plate_number"] == "DL01AB1234"
    assert match_result["fir_number"] == "FIR-402/2026/SEC-379"

    # Verify canonical event was recorded in DB
    event = db_session.query(CanonicalEvent).filter_by(event_uuid=match_result["event_uuid"]).first()
    assert event is not None
    assert event.event_type == "stolen_vehicle_detected"
    assert event.severity == "critical"


def test_person_face_watchlist_matching_and_alert(db_session):
    # Create 512-D synthetic vector for wanted suspect
    synth_wanted_vec = [0.1] * 512
    # Normalize
    norm = sum(x * x for x in synth_wanted_vec) ** 0.5
    synth_wanted_vec = [x / norm for x in synth_wanted_vec]

    person_uuid = "wanted_test_001"
    existing = db_session.query(PersonWatchlist).filter_by(person_uuid=person_uuid).first()
    if not existing:
        person = PersonWatchlist(
            person_uuid=person_uuid,
            full_name="Vikram Malhotra",
            alias="Vicky Shooter",
            category="WANTED_CRIMINAL",
            case_reference="FIR-221/2025/SEC-302",
            face_embedding_json=json.dumps(synth_wanted_vec),
            status="ACTIVE",
            priority="CRITICAL",
        )
        db_session.add(person)
        db_session.commit()

    # 1. Test positive match with identical vector (similarity = 1.0)
    match_res = check_face_against_person_watchlist(
        db=db_session,
        face_embedding=synth_wanted_vec,
        camera_id="cam_02",
        threshold=0.80,
    )
    assert match_res is not None
    assert match_res["matched"] is True
    assert match_res["person_name"] == "Vikram Malhotra"
    assert match_res["score"] >= 0.99
    assert match_res["cctns_dossier"] is not None

    # 2. Test orthogonal/different vector (similarity ~ 0.0) -> returns None
    diff_vec = [0.0] * 256 + [0.1] * 256
    diff_norm = sum(x * x for x in diff_vec) ** 0.5
    diff_vec = [x / diff_norm for x in diff_vec]

    no_match = check_face_against_person_watchlist(
        db=db_session,
        face_embedding=diff_vec,
        camera_id="cam_02",
        threshold=0.85,
    )
    assert no_match is None
