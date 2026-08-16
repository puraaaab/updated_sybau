"""
Migration 002: Phase 4 Compound B-Tree Indexes
Creates compound indices on (camera_id, timestamp) and high-traffic search columns across:
- events (ix_events_camera_timestamp_start, ix_events_camera_event_type)
- faces (ix_faces_camera_timestamp, ix_faces_label_timestamp)
- vehicles (ix_vehicles_camera_timestamp)
- raw_ocr_records (ix_raw_ocr_camera_timestamp)
- scene_captions (ix_scene_captions_camera_timestamp)
- tracks (ix_tracks_camera_last_seen, ix_tracks_label)
"""

from sqlalchemy import text, Connection

MIGRATION_ID = "002_phase4_compound_indexes"


def upgrade(conn: Connection):
    indexes = [
        # Canonical Events compound indexes
        "CREATE INDEX IF NOT EXISTS ix_events_camera_timestamp_start ON events (camera_id, timestamp_start);",
        "CREATE INDEX IF NOT EXISTS ix_events_camera_event_type ON events (camera_id, event_type);",
        
        # Faces compound and label indexes
        "CREATE INDEX IF NOT EXISTS ix_faces_camera_timestamp ON faces (camera_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_faces_label_timestamp ON faces (label, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_faces_label ON faces (label);",
        "CREATE INDEX IF NOT EXISTS ix_faces_timestamp ON faces (timestamp);",
        
        # Vehicles compound and timestamp indexes
        "CREATE INDEX IF NOT EXISTS ix_vehicles_camera_timestamp ON vehicles (camera_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_vehicles_timestamp ON vehicles (timestamp);",
        
        # Raw OCR compound index
        "CREATE INDEX IF NOT EXISTS ix_raw_ocr_camera_timestamp ON raw_ocr_records (camera_id, timestamp);",
        
        # Scene captions compound index
        "CREATE INDEX IF NOT EXISTS ix_scene_captions_camera_timestamp ON scene_captions (camera_id, timestamp);",
        
        # Tracks compound and filter indexes
        "CREATE INDEX IF NOT EXISTS ix_tracks_camera_last_seen ON tracks (camera_id, last_seen);",
        "CREATE INDEX IF NOT EXISTS ix_tracks_label ON tracks (label);",
        "CREATE INDEX IF NOT EXISTS ix_tracks_first_seen ON tracks (first_seen);",
        "CREATE INDEX IF NOT EXISTS ix_tracks_last_seen ON tracks (last_seen);",
    ]

    for stmt in indexes:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 002] Index note: {e}")
