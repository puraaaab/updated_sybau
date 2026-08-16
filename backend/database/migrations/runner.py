"""
Database Migration Runner
Discovers, tracks, and applies versioned database migrations.
"""

import os
import sys
import importlib
import logging
from sqlalchemy import text, inspect
from ..connection import engine, Base

logger = logging.getLogger("vms.migrations")

MIGRATIONS = [
    "001_multi_tenancy_and_user_columns",
    "002_phase4_compound_indexes",
    "003_event_rules_and_skill_registry",
    "004_privilege_elevation_workflow",
    "005_unified_sighting_and_proximity",
    "006_fuzzy_trigram_and_levenshtein",
    "007_camera_topology",
    "008_co_occurrence_clusters",
]


def run_migrations(bind_engine=None):
    """Applies all unapplied migrations to the target database engine."""
    eng = bind_engine or engine
    
    # 1. Ensure tables from Base models exist
    Base.metadata.create_all(bind=eng)

    with eng.connect() as conn:
        # 2. Create applied_migrations table if missing
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                id VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.commit()

        # 3. Read already applied migrations
        applied = {
            row[0] for row in conn.execute(text("SELECT id FROM applied_migrations;")).fetchall()
        }

        # 4. Apply new migrations in order
        for mig_name in MIGRATIONS:
            if mig_name in applied:
                continue

            logger.info(f"[Migrations] Applying migration: {mig_name}...")
            mod = importlib.import_module(f".{mig_name}", package="backend.database.migrations")
            if hasattr(mod, "upgrade"):
                mod.upgrade(conn)
                conn.execute(
                    text("INSERT INTO applied_migrations (id) VALUES (:id);"),
                    {"id": mig_name}
                )
                conn.commit()
                logger.info(f"[Migrations] Successfully applied: {mig_name}")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Running database migrations...")
    run_migrations()
    print("All migrations successfully applied.")
