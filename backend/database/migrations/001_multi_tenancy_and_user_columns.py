"""
Migration 001: Multi-tenancy and User Columns
Adds organization_id, site_id, status, must_change_password, deleted_at across core tables.
"""

from sqlalchemy import text, Connection, inspect

MIGRATION_ID = "001_multi_tenancy_and_user_columns"


def upgrade(conn: Connection):
    dialect_name = conn.dialect.name
    
    if dialect_name == "sqlite":
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        
        sqlite_columns = [
            ("users", "status", "VARCHAR DEFAULT 'active' NOT NULL"),
            ("users", "must_change_password", "BOOLEAN DEFAULT 1 NOT NULL"),
            ("users", "deleted_at", "TIMESTAMP NULL"),
            ("users", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("users", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("cameras", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("cameras", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("tracks", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("tracks", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("tracks", "last_bbox_x", "FLOAT DEFAULT 0.5 NOT NULL"),
            ("tracks", "last_bbox_y", "FLOAT DEFAULT 0.5 NOT NULL"),
            ("faces", "camera_id", "VARCHAR NULL"),
            ("faces", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("faces", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("vehicles", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("vehicles", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("raw_ocr_records", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("raw_ocr_records", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("zones", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("zones", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("custom_alert_rules", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("custom_alert_rules", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
            ("global_identities", "attributes_json", "TEXT DEFAULT '{}' NOT NULL"),
            ("global_identities", "organization_id", "VARCHAR DEFAULT 'org_default' NOT NULL"),
            ("global_identities", "site_id", "VARCHAR DEFAULT 'site_main' NOT NULL"),
        ]
        
        for table, col, col_type in sqlite_columns:
            if table in existing_tables:
                existing_cols = {c["name"] for c in inspector.get_columns(table)}
                if col not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
                    except Exception as e:
                        print(f"[Migration 001] SQLite alter table {table} note: {e}")
    else:
        statements = [
            # Users table extensions
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active' NOT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT TRUE NOT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            
            # Cameras table extensions
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            
            # Tracks table extensions
            "ALTER TABLE tracks ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE tracks ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            "ALTER TABLE tracks ADD COLUMN IF NOT EXISTS last_bbox_x FLOAT DEFAULT 0.5 NOT NULL;",
            "ALTER TABLE tracks ADD COLUMN IF NOT EXISTS last_bbox_y FLOAT DEFAULT 0.5 NOT NULL;",
            
            # Faces table extensions
            "ALTER TABLE faces ADD COLUMN IF NOT EXISTS camera_id VARCHAR NULL;",
            "ALTER TABLE faces ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE faces ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            
            # Vehicles table extensions
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            
            # Raw OCR table extensions
            "ALTER TABLE raw_ocr_records ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE raw_ocr_records ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            
            # Zones & Custom Alert Rules extensions
            "ALTER TABLE zones ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE zones ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            "ALTER TABLE custom_alert_rules ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE custom_alert_rules ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
            
            # Global identities
            "ALTER TABLE global_identities ADD COLUMN IF NOT EXISTS attributes_json TEXT DEFAULT '{}' NOT NULL;",
            "ALTER TABLE global_identities ADD COLUMN IF NOT EXISTS organization_id VARCHAR DEFAULT 'org_default' NOT NULL;",
            "ALTER TABLE global_identities ADD COLUMN IF NOT EXISTS site_id VARCHAR DEFAULT 'site_main' NOT NULL;",
        ]

        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                print(f"[Migration 001] Statement note: {e}")
