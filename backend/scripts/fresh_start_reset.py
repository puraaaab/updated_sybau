import os
import sys
import glob
import shutil

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text
from backend.database.connection import SessionLocal, engine
from backend.ai.model_manager import model_manager

def reset_system_data():
    print("=== SYBAU VMS Fresh Start Data Purge ===")

    # 1. Purge DB tables (preserving Camera, User, Zone, AlertConfig, CustomAlertRule)
    tables_to_clear = [
        "tracks",
        "faces",
        "vehicles",
        "alerts",
        "global_identities",
        "audit_logs",
        "search_history",
        "scene_captions"
    ]

    with engine.begin() as conn:
        for tbl in tables_to_clear:
            try:
                conn.execute(text(f"DELETE FROM {tbl};"))
                print(f"Cleared DB table: {tbl}")
            except Exception as e:
                print(f"Note clearing {tbl}: {e}")

    # 2. Reset vector DB in-memory fallback
    model_manager.vector_db.clear()
    print("Cleared in-memory vector database embeddings.")

    # 3. Purge storage files (snapshots, clips, forensic exports)
    storage_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage"))
    folders_to_clean = ["snapshots", "clips", "forensic_exports"]

    for folder in folders_to_clean:
        dir_path = os.path.join(storage_root, folder)
        if os.path.exists(dir_path):
            count = 0
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                        count += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        count += 1
                except Exception as ex:
                    print(f"Failed deleting {item_path}: {ex}")
            print(f"Purged storage/{folder} ({count} items deleted).")

    # 4. Clear plate storage logs
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
    plates_log = os.path.join(log_dir, "plates_stored.log")
    if os.path.exists(plates_log):
        try:
            with open(plates_log, "w", encoding="utf-8") as f:
                f.write("")
            print("Truncated logs/plates_stored.log.")
        except Exception as e:
            print(f"Note truncating plates log: {e}")

    print("=== Fresh Start Data Purge Complete! Cameras and system settings preserved. ===")

if __name__ == "__main__":
    reset_system_data()
