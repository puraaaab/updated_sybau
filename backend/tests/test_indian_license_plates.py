import pytest
from backend.ai.vehicle.plate_parser import parse_plate

def test_valid_indian_license_plates():
    valid_cases = [
        "MH02AB1234",
        "DL10C5678",
        "KA51MB8811",
        "GJ05CZ1378",
        "GA05CZ1378",
        "HR26DQ5555",
        "WB06A1234",
        "TN09AX9999",
        "22BH1234AA",
        "DL1C1234",
        "UP16B1234",
        "RJ14CB9999",
    ]
    for plate in valid_cases:
        res = parse_plate(plate)
        assert res.get("parsed") is not None, f"Failed to parse valid plate: {plate}"

def test_invalid_raw_ocr_and_internal_ids_rejected():
    invalid_cases = [
        "SAGARTOURSTRAVELSRAIIDERSURATNO8200352801",
        "VEHICLE_9298E6",
        "VEHICLE_5E171E",
        "VEHICLE_11199D",
        "SHOPNAMEENTERPRISES",
        "NO_PARKING_ZONE",
        "RESTRICTED_AREA_KEEP_OUT",
    ]
    for raw in invalid_cases:
        res = parse_plate(raw)
        assert res.get("parsed") is None, f"Invalid text incorrectly parsed as plate: {raw} -> {res.get('parsed')}"
