"""
Migration 003: Event Rules and AI Skill Registry
Creates tables, columns, and indexes for dynamic AI skills and multi-condition event rules.
"""

from sqlalchemy import text, Connection

MIGRATION_ID = "003_event_rules_and_skill_registry"


def upgrade(conn: Connection):
    statements = [
        # AI Skills Registry table
        """
        CREATE TABLE IF NOT EXISTS ai_skills_registry (
            id SERIAL PRIMARY KEY,
            skill_id VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            version VARCHAR(50) NOT NULL,
            model_name VARCHAR(255) NOT NULL,
            input_type VARCHAR(50) DEFAULT 'frame',
            output_schema_json TEXT DEFAULT '{}' NOT NULL,
            hardware_req VARCHAR(50) DEFAULT 'CPU',
            min_fps FLOAT DEFAULT 1.0,
            target_fps FLOAT DEFAULT 5.0,
            max_fps FLOAT DEFAULT 10.0,
            is_enabled BOOLEAN DEFAULT TRUE
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_ai_skills_registry_skill_id ON ai_skills_registry (skill_id);",
        
        # Camera Skill Assignments table
        """
        CREATE TABLE IF NOT EXISTS camera_skill_assignments (
            id SERIAL PRIMARY KEY,
            camera_id VARCHAR(255) NOT NULL,
            skill_id VARCHAR(255) NOT NULL,
            config_json TEXT DEFAULT '{}' NOT NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_camera_skill_assignments_camera_id ON camera_skill_assignments (camera_id);",
        "CREATE INDEX IF NOT EXISTS ix_camera_skill_assignments_skill_id ON camera_skill_assignments (skill_id);",
        
        # Event Rules table
        """
        CREATE TABLE IF NOT EXISTS event_rules (
            id SERIAL PRIMARY KEY,
            rule_id VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            conditions_json TEXT NOT NULL,
            actions_json TEXT NOT NULL,
            severity VARCHAR(50) DEFAULT 'high',
            cooldown_seconds INTEGER DEFAULT 60,
            is_active BOOLEAN DEFAULT TRUE,
            organization_id VARCHAR(255) DEFAULT 'org_default' NOT NULL,
            site_id VARCHAR(255) DEFAULT 'site_main' NOT NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_event_rules_rule_id ON event_rules (rule_id);",
        "CREATE INDEX IF NOT EXISTS ix_event_rules_organization_id ON event_rules (organization_id);",
    ]

    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            print(f"[Migration 003] Statement note: {e}")
