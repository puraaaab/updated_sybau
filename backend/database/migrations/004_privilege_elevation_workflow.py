"""
Migration 004: Privilege Elevation Workflow (FEAT-02)
Creates table privilege_elevation_requests with indexes for TTL expiration and audit tracking.
"""

from sqlalchemy import text, Connection

MIGRATION_ID = "004_privilege_elevation_workflow"


def upgrade(conn: Connection):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS privilege_elevation_requests (
            id SERIAL PRIMARY KEY,
            request_uuid VARCHAR(255) UNIQUE NOT NULL,
            username VARCHAR(255) NOT NULL,
            requested_role VARCHAR(50) DEFAULT 'admin' NOT NULL,
            base_role VARCHAR(50) DEFAULT 'operator' NOT NULL,
            reason TEXT NOT NULL,
            status VARCHAR(50) DEFAULT 'PENDING' NOT NULL,
            ttl_minutes INTEGER DEFAULT 60 NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            reviewed_by VARCHAR(255) NULL,
            reviewed_at TIMESTAMP WITH TIME ZONE NULL,
            expires_at TIMESTAMP WITH TIME ZONE NULL,
            organization_id VARCHAR(255) DEFAULT 'org_default' NOT NULL,
            site_id VARCHAR(255) DEFAULT 'site_main' NOT NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_privilege_elevation_request_uuid ON privilege_elevation_requests (request_uuid);",
        "CREATE INDEX IF NOT EXISTS ix_privilege_elevation_username ON privilege_elevation_requests (username);",
        "CREATE INDEX IF NOT EXISTS ix_privilege_elevation_status ON privilege_elevation_requests (status);",
        "CREATE INDEX IF NOT EXISTS ix_privilege_elevation_expires_at ON privilege_elevation_requests (expires_at);",
    ]

    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 004] Statement note: {e}")
