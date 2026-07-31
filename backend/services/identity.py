import uuid
import datetime
import threading
from sqlalchemy.orm import Session
from ..database.connection import SessionLocal
from ..database.models import GlobalIdentity, Track
from ..search.vector_search import cosine_similarity

_track_identity_cache = {}
_cache_lock = threading.Lock()

class GlobalIdentityManager:
    @staticmethod
    def get_or_create_face_identity(track_uuid: str, camera_id: str, face_embedding: list) -> str:
        """
        Matches a local person track's face embedding against the database
        to merge identities across camera feeds.
        """
        if track_uuid:
            with _cache_lock:
                if track_uuid in _track_identity_cache:
                    return _track_identity_cache[track_uuid]

        db: Session = SessionLocal()
        try:
            identities = db.query(GlobalIdentity).filter(GlobalIdentity.type == "person").all()
            
            best_match = None
            best_score = 0.85
            
            from ..search.qdrant_utils import qdrant_client_with_timeout
            try:
                with qdrant_client_with_timeout(2.0) as client:
                    results = client.query_points(
                        collection_name="vms_embeddings",
                        query=face_embedding,
                        using="face",
                        limit=1
                    ).points
                    if results and results[0].score > best_score:
                        best_score = results[0].score
                        best_match = results[0].payload.get("identity_uuid")
            except Exception as qd_err:
                from ..ai.model_manager import model_manager
                for item in model_manager.vector_db:
                    if item["payload"].get("type") == "face":
                        score = cosine_similarity(face_embedding, item["vector"])
                        if score > best_score:
                            best_score = score
                            best_match = item["payload"].get("identity_uuid")

            res_id = "POI_UNKNOWN"
            if best_match:
                db_id = db.query(GlobalIdentity).filter(GlobalIdentity.identity_uuid == best_match).first()
                if db_id:
                    db_id.last_seen = datetime.datetime.utcnow()
                    db.commit()
                    res_id = db_id.identity_uuid
            else:
                short_uuid = str(uuid.uuid4())[:6].upper()
                new_id = f"POI_{short_uuid}"
                db_id = GlobalIdentity(
                    identity_uuid=new_id,
                    type="person",
                    name=f"Person {short_uuid}",
                    first_seen=datetime.datetime.utcnow(),
                    last_seen=datetime.datetime.utcnow()
                )
                db.add(db_id)
                db.commit()
                res_id = new_id

            if track_uuid:
                with _cache_lock:
                    if len(_track_identity_cache) > 5000:
                        _track_identity_cache.clear()
                    _track_identity_cache[track_uuid] = res_id

            return res_id
        except Exception as e:
            print(f"[IdentityManager] Error matching face identity: {e}")
            return "POI_UNKNOWN"
        finally:
            db.close()

    @staticmethod
    def get_or_create_vehicle_identity(track_uuid: str, camera_id: str, reid_vector: list, license_plate: str = None) -> str:
        """
        Matches a vehicle track's license plate or visual features to merge identities across camera feeds.
        """
        if track_uuid:
            with _cache_lock:
                if track_uuid in _track_identity_cache:
                    return _track_identity_cache[track_uuid]

        db: Session = SessionLocal()
        try:
            res_id = None
            if license_plate and str(license_plate).strip():
                clean_plate = str(license_plate).strip().upper().replace(" ", "")
                plate_id = f"VEHICLE_{clean_plate}"
                db_id = db.query(GlobalIdentity).filter(GlobalIdentity.identity_uuid == plate_id).first()
                if not db_id:
                    db_id = GlobalIdentity(
                        identity_uuid=plate_id,
                        type="vehicle",
                        name=f"Vehicle {clean_plate}",
                        first_seen=datetime.datetime.utcnow(),
                        last_seen=datetime.datetime.utcnow()
                    )
                    db.add(db_id)
                else:
                    db_id.last_seen = datetime.datetime.utcnow()
                db.commit()
                res_id = plate_id
            else:
                best_match = None
                best_score = 0.85
                
                from ..search.qdrant_utils import qdrant_client_with_timeout
                try:
                    with qdrant_client_with_timeout(2.0) as client:
                        results = client.query_points(
                            collection_name="vms_embeddings",
                            query=reid_vector,
                            using="vehicle",
                            limit=1
                        ).points
                        if results and results[0].score > best_score:
                            best_score = results[0].score
                            best_match = results[0].payload.get("identity_uuid")
                except Exception as qd_err:
                    from ..ai.model_manager import model_manager
                    for item in model_manager.vector_db:
                        if item["payload"].get("type") == "vehicle":
                            if len(item.get("vector", [])) == len(reid_vector):
                                score = cosine_similarity(reid_vector, item["vector"])
                                if score > best_score:
                                    best_score = score
                                    best_match = item["payload"].get("identity_uuid")
                            
                if best_match:
                    db_id = db.query(GlobalIdentity).filter(GlobalIdentity.identity_uuid == best_match).first()
                    if db_id:
                        db_id.last_seen = datetime.datetime.utcnow()
                        db.commit()
                        res_id = db_id.identity_uuid

                if not res_id:
                    short_uuid = str(uuid.uuid4())[:6].upper()
                    new_id = f"VEHICLE_{short_uuid}"
                    db_id = GlobalIdentity(
                        identity_uuid=new_id,
                        type="vehicle",
                        name=f"Vehicle {short_uuid}",
                        first_seen=datetime.datetime.utcnow(),
                        last_seen=datetime.datetime.utcnow()
                    )
                    db.add(db_id)
                    db.commit()
                    res_id = new_id

            if track_uuid:
                with _cache_lock:
                    if len(_track_identity_cache) > 5000:
                        _track_identity_cache.clear()
                    _track_identity_cache[track_uuid] = res_id

            return res_id
        except Exception as e:
            print(f"[IdentityManager] Error matching vehicle identity: {e}")
            return "VEHICLE_UNKNOWN"
        finally:
            db.close()
