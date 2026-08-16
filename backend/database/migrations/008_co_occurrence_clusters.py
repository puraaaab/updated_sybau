"""
Migration 008: Spatio-Temporal Co-Occurrence (Convoy & Accomplice Clustering)
Creates co_occurrence_clusters table with human review workflow status indexes.
"""

from sqlalchemy import text, Connection

MIGRATION_ID = "008_co_occurrence_clusters"


def upgrade(conn: Connection):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS co_occurrence_clusters (
            id SERIAL PRIMARY KEY,
            cluster_uuid VARCHAR(64) UNIQUE NOT NULL,
            primary_target_id VARCHAR(128) NOT NULL,
            companion_target_id VARCHAR(128) NOT NULL,
            primary_type VARCHAR(64) DEFAULT 'vehicle' NOT NULL,
            companion_type VARCHAR(64) DEFAULT 'vehicle' NOT NULL,
            sightings_count INTEGER DEFAULT 1 NOT NULL,
            cameras_count INTEGER DEFAULT 1 NOT NULL,
            cameras_involved_json TEXT DEFAULT '[]' NOT NULL,
            avg_time_delta_sec FLOAT DEFAULT 0.0 NOT NULL,
            confidence_score FLOAT DEFAULT 0.0 NOT NULL,
            status VARCHAR(64) DEFAULT 'FLAGGED_PENDING_REVIEW' NOT NULL,
            reviewed_by VARCHAR(64) NULL,
            reviewed_at TIMESTAMP WITH TIME ZONE NULL,
            review_notes TEXT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_co_occurrence_primary ON co_occurrence_clusters (primary_target_id);",
        "CREATE INDEX IF NOT EXISTS ix_co_occurrence_companion ON co_occurrence_clusters (companion_target_id);",
        "CREATE INDEX IF NOT EXISTS ix_co_occurrence_status ON co_occurrence_clusters (status);",
    ]

    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 008] Statement note: {e}")
