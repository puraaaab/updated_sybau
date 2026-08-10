import os
import shutil
import glob
import sys

# Ensure UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def reset_all_data():
    print("[RESET] Starting fresh data wipe across Sybau VMS...")

    # 1. Clear Database Tables via SQLAlchemy
    try:
        from backend.database.connection import SessionLocal
        from backend.database.models import Track, Face, Vehicle, RawOCR, Alert, SceneCaption, GlobalIdentity, SearchHistory, CustomAlertRule

        with SessionLocal() as db:
            print("  • Clearing SQL database tables (tracks, faces, vehicles, raw_ocr, alerts, captions, identities, search history)...")
            db.query(Track).delete()
            db.query(Face).delete()
            db.query(Vehicle).delete()
            db.query(RawOCR).delete()
            db.query(Alert).delete()
            db.query(SceneCaption).delete()
            db.query(GlobalIdentity).delete()
            db.query(SearchHistory).delete()
            db.query(CustomAlertRule).delete()
            db.commit()
        print("    [OK] SQL database tables cleared.")
    except Exception as e:
        print(f"    [NOTE] SQL database clear notice: {e}")

    # 2. Clear Local SQLite Files if present
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sqlite_files = ["vms.db", "vms.db-shm", "vms.db-wal"]
    for sqf in sqlite_files:
        fp = os.path.join(base_dir, sqf)
        if os.path.exists(fp):
            try:
                os.remove(fp)
                print(f"    [OK] Local SQLite file {sqf} removed.")
            except Exception as e:
                print(f"    [NOTE] Note removing {sqf}: {e}")

    # 3. Clear Qdrant Vector Collection
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

    # 4. Clear Snapshots and Recordings
    snap_dir = os.path.join(base_dir, "storage", "snapshots")
    rec_dir = os.path.join(base_dir, "storage", "recordings")

    if os.path.exists(snap_dir):
        for f in glob.glob(os.path.join(snap_dir, "*")):
            try:
                if os.path.isfile(f):
                    os.remove(f)
            except Exception:
                pass
        print("    [OK] Storage snapshots directory cleared.")

    if os.path.exists(rec_dir):
        for f in glob.glob(os.path.join(rec_dir, "*")):
            try:
                if os.path.isfile(f):
                    os.remove(f)
                elif os.path.isdir(f):
                    shutil.rmtree(f)
            except Exception:
                pass
        print("    [OK] Storage recordings directory cleared.")

    # 5. Clear Log Files
    plates_log = os.path.join(base_dir, "logs", "plates_stored.log")
    if os.path.exists(plates_log):
        with open(plates_log, "w", encoding="utf-8") as f:
            f.write("")
        print("    [OK] License plates log cleared.")

    print("\n[COMPLETE] Fresh start reset complete! All historical data, captions, face vectors, vehicle records, and snapshots have been erased.")

if __name__ == "__main__":
    reset_all_data()
