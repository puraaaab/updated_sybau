"""
Migration 006: PostgreSQL Fuzzy Trigram (pg_trgm) & Levenshtein Matching
Enables pg_trgm and fuzzystrmatch extensions, creates GIN trigram indexes for sub-millisecond fuzzy searches.
"""

from sqlalchemy import text, Connection

MIGRATION_ID = "006_fuzzy_trigram_and_levenshtein"


def upgrade(conn: Connection):
    dialect_name = conn.dialect.name
    if dialect_name != "postgresql":
        # SQLite doesn't support pg_trgm extensions or GIN indexes.
        # Standard indexes on extracted text and license plates are sufficient for SQLite fallback.
        sqlite_indexes = [
            "CREATE INDEX IF NOT EXISTS ix_raw_ocr_raw_text ON raw_ocr_records (raw_text);",
            "CREATE INDEX IF NOT EXISTS ix_raw_ocr_detected_text ON raw_ocr_records (detected_text);",
            "CREATE INDEX IF NOT EXISTS ix_vehicle_plate_num ON vehicle_journey_events (license_plate);",
            "CREATE INDEX IF NOT EXISTS ix_unified_text_extracted ON unified_sightings (extracted_text);",
        ]
        for stmt in sqlite_indexes:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                print(f"[Migration 006] SQLite index note: {e}")
        return

    statements = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
        "CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;",
        "CREATE INDEX IF NOT EXISTS ix_raw_ocr_raw_trgm ON raw_ocr_records USING gin (raw_text gin_trgm_ops);",
        "CREATE INDEX IF NOT EXISTS ix_raw_ocr_detected_trgm ON raw_ocr_records USING gin (detected_text gin_trgm_ops);",
        "CREATE INDEX IF NOT EXISTS ix_vehicle_plate_trgm ON vehicle_journey_events USING gin (license_plate gin_trgm_ops);",
        "CREATE INDEX IF NOT EXISTS ix_unified_text_trgm ON unified_sightings USING gin (extracted_text gin_trgm_ops);",
    ]

    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 006] Statement note: {e}")
