import os
import shutil
import glob
import sys

# Ensure UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def reset_all_data():
    print("[RESET] Starting fresh data wipe across Sybau VMS...")

    # 1. Clear Database Tables via SQLAlchemy (preserving Cameras, Users, and Zones)
    try:
        from backend.database.connection import SessionLocal, engine
        from sqlalchemy import text

        tables_to_clear = [
            "tracks",
            "faces",
            "vehicles",
            "canonical_events",
            "alerts",
            "unified_sightings",
            "global_identities",
            "audit_logs",
            "user_query_audit_logs",
            "search_history",
            "scene_captions",
            "raw_ocr_records"
        ]

        with engine.begin() as conn:
            print("  • Clearing SQL database tables (tracks, faces, vehicles, raw_ocr, alerts, captions, identities, search history)...")
            for tbl in tables_to_clear:
                try:
                    conn.execute(text(f"DELETE FROM {tbl};"))
                    print(f"    [OK] Cleared table: {tbl}")
                except Exception as tbl_err:
                    pass
        print("    [OK] SQL database analytical tables cleared (Cameras, Users, and Zones preserved).")
    except Exception as e:
        print(f"    [NOTE] SQL database clear notice: {e}")

    # 2. Clear Qdrant Vector Collection
    try:
        print("  • Recreating Qdrant collection 'vms_embeddings'...")
        from backend.search.qdrant_utils import get_qdrant_client
        client = get_qdrant_client()
        if client:
            from qdrant_client.http import models as qmodels
            try:
                client.delete_collection("vms_embeddings")
            except Exception:
                pass

            client.create_collection(
                collection_name="vms_embeddings",
                vectors_config={
                    "face": qmodels.VectorParams(size=128, distance=qmodels.Distance.COSINE),
                    "scene": qmodels.VectorParams(size=1024, distance=qmodels.Distance.COSINE),
                    "vehicle": qmodels.VectorParams(size=576, distance=qmodels.Distance.COSINE),
                    "person_crop": qmodels.VectorParams(size=768, distance=qmodels.Distance.COSINE)
                }
            )
            print("    [OK] Qdrant vector database collection reset.")
    except Exception as e:
        print(f"    [NOTE] Qdrant collection reset notice: {e}")

    # 3. Clear Snapshots, Clips, and Recordings
    storage_root = os.path.join(PROJECT_ROOT, "storage")
    folders_to_clean = ["snapshots", "recordings", "clips", "forensic_exports"]

    for folder in folders_to_clean:
        dir_path = os.path.join(storage_root, folder)
        if os.path.exists(dir_path):
            count = 0
            for root, dirs, files in os.walk(dir_path, topdown=False):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        os.unlink(fp)
                        count += 1
                    except Exception:
                        pass
                for d in dirs:
                    dp = os.path.join(root, d)
                    try:
                        os.rmdir(dp)
                    except Exception:
                        pass
            print(f"    [OK] Storage/{folder} cleared ({count} items deleted).")

    # 4. Clear Log Files
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    plates_log = os.path.join(log_dir, "plates_stored.log")
    if os.path.exists(plates_log):
        try:
            with open(plates_log, "w", encoding="utf-8") as f:
                f.write("")
            print("    [OK] License plates log cleared.")
        except Exception as e:
            print(f"    [NOTE] Truncating plates log notice: {e}")

    print("\n[COMPLETE] Fresh start reset complete! All historical data, captions, face vectors, vehicle records, and snapshots have been erased. Camera seeding and system settings were preserved.")

if __name__ == "__main__":
    reset_all_data()

