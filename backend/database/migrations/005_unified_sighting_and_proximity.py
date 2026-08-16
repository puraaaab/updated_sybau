"""
Migration 005: Unified Multi-Modal Sightings and Proximity Scale
Adds proximity_scale to cameras, creates unified_sightings and query_audit_logs tables.
"""

from sqlalchemy import text, Connection, inspect

MIGRATION_ID = "005_unified_sighting_and_proximity"


def upgrade(conn: Connection):
    dialect_name = conn.dialect.name

    if dialect_name == "sqlite":
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        if "cameras" in existing_tables:
            existing_cols = {c["name"] for c in inspector.get_columns("cameras")}
            if "proximity_scale" not in existing_cols:
                try:
                    conn.execute(text("ALTER TABLE cameras ADD COLUMN proximity_scale FLOAT DEFAULT 1.25;"))
                except Exception as e:
                    print(f"[Migration 005] SQLite alter table cameras note: {e}")
    else:
        try:
            conn.execute(text("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS proximity_scale FLOAT DEFAULT 1.25;"))
        except Exception as e:
            print(f"[Migration 005] Statement note: {e}")

    statements = [
        """
        CREATE TABLE IF NOT EXISTS unified_sightings (
            id SERIAL PRIMARY KEY,
            sighting_uuid VARCHAR(64) UNIQUE NOT NULL,
            camera_id VARCHAR(64) NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            track_uuid VARCHAR(128) NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            primary_class VARCHAR(64) NOT NULL,
            confidence FLOAT DEFAULT 0.0,
            bbox_json TEXT DEFAULT '[0, 0, 0, 0]' NOT NULL,
            speed_kmh FLOAT DEFAULT 0.0,
            raw_ocr_id INTEGER NULL REFERENCES raw_ocr_records(id) ON DELETE SET NULL,
            scene_caption_id INTEGER NULL REFERENCES scene_captions(id) ON DELETE SET NULL,
            vehicle_event_id INTEGER NULL REFERENCES vehicle_journey_events(id) ON DELETE SET NULL,
            face_id INTEGER NULL REFERENCES faces(id) ON DELETE SET NULL,
            extracted_text VARCHAR(512) NULL,
            license_plate VARCHAR(32) NULL,
            visual_description TEXT NULL,
            attributes_json TEXT DEFAULT '{}' NOT NULL,
            snapshot_url VARCHAR(512) NULL,
            nearby_pedestrian_uuids TEXT DEFAULT '[]' NOT NULL,
            proximity_flag VARCHAR(64) DEFAULT 'ESTIMATED_DEPTH_PROXY',
            organization_id VARCHAR(64) DEFAULT 'org_default' NOT NULL,
            site_id VARCHAR(64) DEFAULT 'site_main' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_unified_cam_time ON unified_sightings (camera_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_unified_track ON unified_sightings (track_uuid);",
        "CREATE INDEX IF NOT EXISTS ix_unified_plate ON unified_sightings (license_plate);",
        "CREATE INDEX IF NOT EXISTS ix_unified_class ON unified_sightings (primary_class);",
        """
        CREATE TABLE IF NOT EXISTS query_audit_logs (
            id SERIAL PRIMARY KEY,
            session_uuid VARCHAR(64) NULL,
            username VARCHAR(64) DEFAULT 'operator' NOT NULL,
            query_text TEXT NOT NULL,
            search_mode VARCHAR(32) DEFAULT 'all' NOT NULL,
            matched_records_count INTEGER DEFAULT 0,
            matched_sighting_ids TEXT DEFAULT '[]' NOT NULL,
            ip_address VARCHAR(45) NULL,
            execution_time_ms FLOAT DEFAULT 0.0,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_query_audit_user_time ON query_audit_logs (username, timestamp);",
    ]

    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 005] Statement note: {e}")
