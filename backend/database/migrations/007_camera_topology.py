"""
Migration 007: Camera Topology & Predictive Transit Routing
Creates camera_nodes and camera_edges tables with user-editable coordinate support.
"""

from sqlalchemy import text, Connection

MIGRATION_ID = "007_camera_topology"


def upgrade(conn: Connection):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS camera_nodes (
            camera_id VARCHAR(64) PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
            label VARCHAR(128) NOT NULL,
            geo_lat FLOAT NULL,
            geo_lng FLOAT NULL,
            map_x FLOAT DEFAULT 150.0 NOT NULL,
            map_y FLOAT DEFAULT 150.0 NOT NULL,
            zone_group VARCHAR(64) DEFAULT 'Main City' NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS camera_edges (
            id SERIAL PRIMARY KEY,
            source_camera_id VARCHAR(64) NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            target_camera_id VARCHAR(64) NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            distance_meters FLOAT DEFAULT 500.0,
            expected_transit_sec_min INTEGER DEFAULT 60 NOT NULL,
            expected_transit_sec_max INTEGER DEFAULT 300 NOT NULL,
            allowed_directions TEXT DEFAULT '["forward"]' NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            CONSTRAINT unique_camera_edge UNIQUE (source_camera_id, target_camera_id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_camera_edges_source ON camera_edges (source_camera_id);",
        "CREATE INDEX IF NOT EXISTS ix_camera_edges_target ON camera_edges (target_camera_id);",
    ]

    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 007] Statement note: {e}")
