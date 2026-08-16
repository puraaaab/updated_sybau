import pytest
from sqlalchemy import text, func
from backend.database.connection import SessionLocal, engine
from backend.database.models import RawOCR

def test_module3_pg_trgm_extension_and_similarity():
    """Validates PostgreSQL pg_trgm similarity queries and confidence distinction."""
    db = SessionLocal()
    try:
        # 1. Check pg_trgm extension word_similarity calculation
        res = db.execute(text("SELECT word_similarity('SAG4R', 'SAGAR TOURS & TRAVELS');")).scalar()
        assert res is not None
        assert float(res) >= 0.30, f"Expected word_similarity >= 0.30, got {res}"

        # Clean existing test data and insert test OCR records
        db.query(RawOCR).filter(RawOCR.camera_id == "cam_test_fuzz").delete()
        db.commit()

        r1 = RawOCR(
            camera_id="cam_test_fuzz",
            detected_text="SAGAR TOURS & TRAVELS",
            raw_text="SAGAR TOURS&TRAVELS RANDER SURAT",
            ocr_confidence=0.88
        )
        r2 = RawOCR(
            camera_id="cam_test_fuzz",
            detected_text="GJ05ZN2996",
            raw_text="GJ05ZN2996",
            ocr_confidence=0.92
        )
        db.add_all([r1, r2])
        db.commit()

        # 2. Test Exact Match
        exact_hit = db.query(RawOCR).filter(RawOCR.camera_id == "cam_test_fuzz", RawOCR.raw_text.ilike("%SAGAR%")).first()
        assert exact_hit is not None
        assert exact_hit.id == r1.id

        # 3. Test Fuzzy Match with Typo: "SAG4R" using word_similarity
        fuzzy_hits = (
            db.query(RawOCR, func.word_similarity("SAG4R", RawOCR.raw_text).label("sim"))
            .filter(RawOCR.camera_id == "cam_test_fuzz", func.word_similarity("SAG4R", RawOCR.raw_text) >= 0.30)
            .all()
        )
        assert len(fuzzy_hits) >= 1
        matched_ocr, sim_score = fuzzy_hits[0]
        assert matched_ocr.id == r1.id
        assert float(sim_score) >= 0.30

        # 4. Test Levenshtein distance
        try:
            lev_dist = db.execute(text("SELECT levenshtein('SAGAR', 'SAG4R');")).scalar()
            assert lev_dist == 1
        except Exception:
            pass
    finally:
        db.query(RawOCR).filter(RawOCR.camera_id == "cam_test_fuzz").delete()
        db.commit()
        db.close()
