"""
CCTNS (Crime and Criminal Tracking Network & Systems) Mock Integration Service
================================================================================
Provides realistic state police crime record lookup, FIR history, warrant checks,
and vehicle blacklists for investigative officer situational awareness.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Realistic state police crime fixture database
_MOCK_CCTNS_VEHICLES: Dict[str, Dict[str, Any]] = {
    "DL01AB1234": {
        "plate_number": "DL01AB1234",
        "vehicle_make_model": "Maruti Swift Dzire",
        "vehicle_color": "White",
        "vehicle_type": "car",
        "owner_name": "Rajesh Kumar",
        "fir_number": "FIR-402/2026/SEC-379",
        "police_station": "Connaught Place PS, New Delhi",
        "theft_date": "2026-08-10T14:30:00+05:30",
        "status": "WANTED_STOLEN",
        "charges": "IPC Section 379 (Theft of Motor Vehicle)",
        "warrant_active": True,
        "investigating_officer": "SI Vikram Singh (Badge #8941)",
        "risk_level": "CRITICAL",
    },
    "HR26DK9901": {
        "plate_number": "HR26DK9901",
        "vehicle_make_model": "Hyundai Creta",
        "vehicle_color": "Black",
        "vehicle_type": "suv",
        "owner_name": "Sunil Gurjar",
        "fir_number": "FIR-819/2026/SEC-392",
        "police_station": "DLF Phase 1 PS, Gurugram",
        "theft_date": "2026-08-12T09:15:00+05:30",
        "status": "WANTED_ARMED_ROBBERY",
        "charges": "IPC Section 392/397 (Robbery with deadly weapon)",
        "warrant_active": True,
        "investigating_officer": "Insp. Ravinder Hooda (Badge #4412)",
        "risk_level": "CRITICAL",
    },
    "UP16Z1002": {
        "plate_number": "UP16Z1002",
        "vehicle_make_model": "Honda City",
        "vehicle_color": "Silver",
        "vehicle_type": "car",
        "owner_name": "Amit Sharma",
        "fir_number": "FIR-120/2026/SEC-279",
        "police_station": "Sector 20 PS, Noida",
        "theft_date": "2026-08-14T21:00:00+05:30",
        "status": "HIT_AND_RUN_WANTED",
        "charges": "IPC Section 279/304A (Rash Driving & Culpable Homicide)",
        "warrant_active": True,
        "investigating_officer": "SI Meena Roy (Badge #6720)",
        "risk_level": "HIGH",
    },
    "MH02CB8492": {
        "plate_number": "MH02CB8492",
        "vehicle_make_model": "Toyota Fortuner",
        "vehicle_color": "White",
        "vehicle_type": "suv",
        "owner_name": "Karan Singhania",
        "fir_number": "FIR-993/2026/SEC-420",
        "police_station": "Andheri West PS, Mumbai",
        "theft_date": "2026-08-08T18:45:00+05:30",
        "status": "IMPOUND_ORDER_ACTIVE",
        "charges": "IPC Section 420/468 (Forgery & Smuggling)",
        "warrant_active": False,
        "investigating_officer": "Insp. Sanjay Patil (Badge #2109)",
        "risk_level": "MEDIUM",
    },
}

_MOCK_CCTNS_PERSONS: Dict[str, Dict[str, Any]] = {
    "vikram_malhotra": {
        "full_name": "Vikram Malhotra",
        "alias": "Vicky Shooter",
        "age": 34,
        "gender": "Male",
        "cctns_id": "CCTNS-ND-2024-88912",
        "category": "HISTORY_SHEETER_A_CLASS",
        "active_firs": [
            {"fir": "FIR-221/2025", "sections": "IPC 302/120B (Murder & Conspiracy)", "ps": "Hauz Khas PS"},
            {"fir": "FIR-554/2026", "sections": "Arms Act Section 25/54", "ps": "Saket PS"},
        ],
        "warrant_status": "NON_BAILABLE_WARRANT_ACTIVE",
        "gang_affiliation": "South Delhi Extortion Syndicate",
        "threat_level": "EXTREME",
        "last_known_address": "Block C, Sangam Vihar, New Delhi",
    },
    "rahul_verma": {
        "full_name": "Rahul Verma",
        "alias": "Bunty",
        "age": 28,
        "gender": "Male",
        "cctns_id": "CCTNS-HR-2025-10492",
        "category": "WANTED_ROBBERY_SUSPECT",
        "active_firs": [
            {"fir": "FIR-819/2026", "sections": "IPC 392 (Armed Robbery)", "ps": "DLF Phase 1 PS"},
        ],
        "warrant_status": "LOOKOUT_CIRCULAR_ISSUED",
        "gang_affiliation": "Highway Bike Snatching Ring",
        "threat_level": "HIGH",
        "last_known_address": "Old Railway Road, Gurugram",
    },
    "aarav_sharma": {
        "full_name": "Aarav Sharma",
        "alias": "Chhotu",
        "age": 8,
        "gender": "Male",
        "cctns_id": "CCTNS-MP-2026-00412",
        "category": "MISSING_CHILD",
        "active_firs": [
            {"fir": "MISSING-PERSON-REP-112/2026", "sections": "Missing Child Report (SOP TrackChild)", "ps": "Civil Lines PS"},
        ],
        "warrant_status": "ACTIVE_TRACE_REQUEST",
        "parent_contact": "+91-98765-43210 (Mother: Sunita Sharma)",
        "threat_level": "HIGH_VULNERABILITY",
        "missing_since": "2026-08-15T10:00:00+05:30",
    },
}


def _clean_plate(plate: str) -> str:
    """Normalize license plate to alphanumeric uppercase."""
    return re.sub(r"[^A-Za-z0-9]", "", plate).upper()


def lookup_cctns_vehicle(plate_number: str) -> Optional[Dict[str, Any]]:
    """
    Search CCTNS state repository for a vehicle by license plate.
    Returns full police case sheet if found, else None.
    """
    cleaned = _clean_plate(plate_number)
    for plate_key, record in _MOCK_CCTNS_VEHICLES.items():
        if _clean_plate(plate_key) == cleaned or cleaned.endswith(_clean_plate(plate_key)[-4:]):
            return record
    return None


def lookup_cctns_person(name_or_alias: str) -> Optional[Dict[str, Any]]:
    """
    Search CCTNS state repository for criminal history / missing person dossier.
    """
    query = name_or_alias.strip().lower()
    for key, record in _MOCK_CCTNS_PERSONS.items():
        if query in key or query in record["full_name"].lower() or query in record.get("alias", "").lower():
            return record
    return None


def get_all_active_stolen_vehicles() -> List[Dict[str, Any]]:
    """Return all active stolen vehicle records for hot-list synchronization."""
    return list(_MOCK_CCTNS_VEHICLES.values())


def get_all_wanted_persons() -> List[Dict[str, Any]]:
    """Return all active wanted / missing person dossiers."""
    return list(_MOCK_CCTNS_PERSONS.values())
