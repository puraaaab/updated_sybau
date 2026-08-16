import os
import sys
import shutil
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env')))

from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import (
    User, Camera, CanonicalEvent, Track, Face, Vehicle, RawOCR,
    GlobalIdentity, PersonJourneyEvent, VehicleJourneyEvent, AudioEvent,
    EvidenceLedger, EvidenceChainOfCustody, Investigation,
    SceneCaption, SearchHistory, ChatSession, ChatMessage,
    PrivilegeElevationRequest, AuditLog
)
from backend.search.qdrant_utils import get_qdrant_client


def reset_all_vms_data():
    print("==========================================================")
    print("       VMS COMPLETE TELEMETRY & MEMORY RESET              ")
    print("==========================================================")

    # 1. Clear Database Tables (preserving cameras & users)
    db = SessionLocal()
    try:
        models_to_clear = [
            ("Alerts & Canonical Events", CanonicalEvent),
            ("Tracks", Track),
            ("Faces", Face),
            ("Vehicles", Vehicle),
            ("Raw OCR Records", RawOCR),
            ("Global Identities", GlobalIdentity),
            ("Person Journey Events", PersonJourneyEvent),
            ("Vehicle Journey Events", VehicleJourneyEvent),
            ("Audio Events", AudioEvent),
            ("Evidence Ledger", EvidenceLedger),
            ("Evidence Chain of Custody", EvidenceChainOfCustody),
            ("Investigations", Investigation),
            ("Scene Captions", SceneCaption),
            ("Search History", SearchHistory),
            ("Chat Sessions", ChatSession),
            ("Chat Messages", ChatMessage),
            ("Privilege Requests", PrivilegeElevationRequest),
            ("Audit Logs", AuditLog),
        ]

        print("[DATABASE] Purging telemetry records...")
        for name, model in models_to_clear:
            try:
                deleted_count = db.query(model).delete()
                print(f"  - {name}: {deleted_count} records cleared.")
            except Exception as e:
                print(f"  - {name}: Skipped ({e})")

        db.commit()
        cam_count = db.query(Camera).count()
        user_count = db.query(User).count()
        print(f"[DATABASE] Preserved: {cam_count} Seeded Cameras, {user_count} User Accounts.")

    except Exception as e:
        db.rollback()
        print(f"[DATABASE] Error during table purge: {e}")
    finally:
        db.close()

    # 2. Reset Qdrant Vector Collections
    try:
        client = get_qdrant_client()
        collections_res = client.get_collections()
        col_names = [c.name for c in collections_res.collections]
        
        print(f"[QDRANT] Found {len(col_names)} collections to reset...")
        for col_name in col_names:
            print(f"  - Wiping vectors from collection '{col_name}'...")
            client.delete_collection(col_name)
            client.create_collection(
                collection_name=col_name,
                vectors_config={
                    "text": {"size": 384, "distance": "Cosine"},
                    "vehicle": {"size": 576, "distance": "Cosine"},
                    "face": {"size": 512, "distance": "Cosine"}
                }
            )
            print(f"  - Re-created clean collection '{col_name}'.")
        print("[QDRANT] Qdrant vector memory reset to 0.")
    except Exception as e:
        print(f"[QDRANT] Notice: {e}")

    # 3. Purge Local Snapshots
    snapshots_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'snapshots'))
    if os.path.exists(snapshots_dir):
        files_deleted = 0
        for f in os.listdir(snapshots_dir):
            file_path = os.path.join(snapshots_dir, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    files_deleted += 1
            except Exception:
                pass
        print(f"[FILES] Purged {files_deleted} local snapshot images.")

    # 4. Purge Exports
    exports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'exports'))
    if os.path.exists(exports_dir):
        exports_deleted = 0
        for f in os.listdir(exports_dir):
            file_path = os.path.join(exports_dir, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    exports_deleted += 1
            except Exception:
                pass
        print(f"[FILES] Purged {exports_deleted} export files.")

    print("==========================================================")
    print("  FRESH START COMPLETE — ALL METRICS & RECORDS ARE RESET  ")
    print("==========================================================")


if __name__ == "__main__":
    reset_all_vms_data()
