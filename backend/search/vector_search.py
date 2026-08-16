import logging
import os
import json

import numpy as np

from ..ai.model_manager import model_manager
from ..ai.embeddings.embedder import get_text_embedding
from ..config.service import get_models

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo seed data – populated once at import time so the search page has
# something to show even before any real camera frames are processed.
#
# NOTE: if you populate _DEMO_RECORDS with real entries later, be aware this
# runs at *import time*. If this module ever gets imported from a background
# worker thread while demo_mode is False, the get_text_embedding() calls
# below would lazily load SentenceTransformer on that thread — the same
# thread-safety hazard the Florence pre_warm() step is designed to avoid.
# Prefer seeding explicitly from the main thread at startup rather than
# relying on import side effects, or guard this behind an explicit
# pre_warm()-style call.
# ---------------------------------------------------------------------------

_DEMO_RECORDS = []

STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "of", "and", "is", "are",
    "some", "showing", "shows", "image", "still", "from", "cctv",
    "footage", "with", "there", "has", "have", "by", "for", "to",
    "near", "walking", "standing", "sitting", "people", "street", "road"
}

_TEXT_REPLACEMENTS = {
    "tshirt": "shirt", "t shirt": "shirt",
    "guy": "man", "boy": "man", "gentleman": "man",
    "girl": "woman", "lady": "woman",
    "tuktuk": "rickshaw", "tuk-tuk": "rickshaw",
    "auto": "rickshaw", "auto-rickshaw": "rickshaw",
    "automobile": "car", "sedan": "car", "suv": "car",
    # BUG-05 FIX: motorcycle synonyms so 'bike' and 'motorbike' queries work
    "bike": "motorcycle", "motorbike": "motorcycle", "moto": "motorcycle",
    "footpath": "sidewalk", "pavement": "sidewalk",
    "handbag": "bag", "backpack": "bag", "purse": "bag"
}


def normalize_text(text: str) -> str:
    text = text.lower().replace("-", " ").strip()
    for old, new in _TEXT_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


_COLORS = {
    "black", "white", "red", "blue", "green", "yellow", "silver", "gray", "grey",
    "dark", "cyan", "orange", "brown", "purple", "pink", "maroon", "gold", "light"
}

_VEHICLE_SYNONYMS = {
    "car": ["car", "sedan", "suv", "automobile", "hatchback", "coupe", "jeep", "creta", "swift", "baleno", "innova", "scorpio", "bolero", "ertiga", "fortuner", "nexon", "brezza", "venue", "wagonr", "altroz", "harrier", "safari", "thar"],
    "motorcycle": ["motorcycle", "bike", "motorbike", "scooter", "scooty", "moped", "activa", "splendor", "pulsar", "bullet", "royalenfield", "apache", "shine", "platina", "jupiter"],
    "bus": ["bus", "minibus", "volvo", "traveler"],
    "truck": ["truck", "lorry", "tempo", "dumper", "eicher"],
    "rickshaw": ["rickshaw", "auto", "tuk-tuk", "tuktuk", "auto-rickshaw"],
    "van": ["van", "omni", "eeco", "ambulance"],
    "bicycle": ["bicycle", "cycle"]
}

_PERSON_SYNONYMS = ["person", "man", "woman", "guy", "lady", "boy", "girl", "pedestrian", "individual", "suspect"]


def _keyword_boost(query_text: str, candidate_text: str) -> float:
    """
    Intelligent attribute-aware semantic boost & penalty calculation.
    Enforces true compound matching and penalizes contradiction or missing target objects.
    """
    q_norm = normalize_text(query_text)
    c_norm = normalize_text(candidate_text)
    q_tokens = [w for w in q_norm.split() if w not in STOPWORDS]
    if not q_tokens:
        return 0.0

    # 1. Check exact query substring in candidate text
    if q_norm in c_norm:
        return 0.40

    # 2. Extract query colors and vehicle/person classes
    q_colors = [w for w in q_tokens if w in _COLORS]
    
    q_vclass = None
    for vcat, vlist in _VEHICLE_SYNONYMS.items():
        if any(v in q_tokens for v in vlist):
            q_vclass = vcat
            break

    q_is_person = any(p in q_tokens for p in _PERSON_SYNONYMS)

    # 3. Vehicle-specific attribute verification
    if q_vclass:
        synonyms = _VEHICLE_SYNONYMS[q_vclass]
        has_vclass = any(syn in c_norm for syn in synonyms)
        
        if not has_vclass:
            # Candidate scene has NO instances of the requested vehicle category
            return -0.45

        if q_colors:
            has_compound = False
            for col in q_colors:
                col_variants = [col, "dark"] if col == "black" else [col]
                for cv in col_variants:
                    for syn in synonyms:
                        if f"{cv} {syn}" in c_norm:
                            has_compound = True
                            break
                    if has_compound:
                        break

            if has_compound:
                return 0.45
            else:
                # Target vehicle category is present, but NO instance matches requested color
                return -0.35

        return 0.25

    # 4. Person-specific attribute verification
    if q_is_person:
        has_person = any(syn in c_norm for syn in _PERSON_SYNONYMS)
        if not has_person:
            return -0.45

        if q_colors:
            has_clothing_match = False
            for col in q_colors:
                for piece in ["top", "shirt", "upper", "bottom", "pants", "dress", "jacket", "tshirt", "backpack", "bag", "hoodie"]:
                    if f"{col} {piece}" in c_norm:
                        has_clothing_match = True
                        break
            if has_clothing_match:
                return 0.40
            else:
                return -0.20
        return 0.20

    # 5. General token overlap calculation
    c_tokens = set(c_norm.split())
    matched = [w for w in q_tokens if w in c_tokens]
    if len(matched) == len(q_tokens):
        return 0.35
    elif matched:
        return float(len(matched) / len(q_tokens)) * 0.15

    return 0.0


def _seed_demo_vector_db():
    """Populate model_manager.vector_db with demo records if demo_mode is enabled and DB is empty."""
    cfg = get_models()
    if not cfg.get("demo_mode", False):
        return
    if model_manager.vector_db:
        return  # already seeded (e.g. real frames arrived)
    for rec in _DEMO_RECORDS:
        text = " ".join([
            rec["payload"].get("caption", ""),
            rec["payload"].get("vehicle_type", ""),
            rec["payload"].get("license_plate", ""),
            rec["payload"].get("label", "")
        ]).strip()
        rec["vector"] = get_text_embedding(text)
        model_manager.vector_db.append(rec)


_seed_demo_vector_db()


def cosine_similarity(v1, v2):
    dot = np.dot(v1, v2)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(dot / (n1 * n2))


def _local_text_matches(query_text: str, limit: int, start_time: str = None, end_time: str = None) -> list:
    """In-memory keyword-overlap fallback search over seeded/local records."""
    matches = []
    for item in model_manager.vector_db:
        if item["payload"].get("type") not in ("scene", "vehicle"):
            continue
        
        # Time-range filtering
        item_ts = item["payload"].get("timestamp")
        if item_ts:
            if start_time and item_ts < start_time:
                continue
            if end_time and item_ts > end_time:
                continue

        text_to_compare = " ".join(filter(None, [
            str(item["payload"].get("caption") or ""),
            str(item["payload"].get("vehicle_type") or ""),
            str(item["payload"].get("vehicle_color") or ""),
            str(item["payload"].get("license_plate") or "")
        ])).strip()

        q_norm = normalize_text(query_text)
        c_norm = normalize_text(text_to_compare)
        q_words = {w for w in q_norm.split() if w not in STOPWORDS}
        c_words = {w for w in c_norm.split() if w not in STOPWORDS}
        if not q_words:
            continue

        score = float(len(q_words & c_words) / len(q_words))
        if q_norm and q_norm in c_norm:
            score += 0.5
        score = min(score, 0.99)

        if score >= 0.2:
            matches.append({"score": score, "payload": item["payload"]})

    matches = sorted(matches, key=lambda x: x["score"], reverse=True)
    return matches[:limit]


def _build_qdrant_time_filter(start_time: str = None, end_time: str = None):
    """Constructs a Qdrant Filter with FieldCondition for timestamp range if start_time/end_time are provided."""
    if not start_time and not end_time:
        return None
    try:
        from qdrant_client.http import models as qmodels
        range_kwargs = {}
        if start_time:
            range_kwargs["gte"] = start_time
        if end_time:
            range_kwargs["lte"] = end_time
        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="timestamp",
                    range=qmodels.Range(**range_kwargs)
                )
            ]
        )
    except Exception as e:
        logger.warning("Could not construct Qdrant time filter: %s", e)
        return None


def _sql_text_matches(query_text: str, limit: int = 10, start_time: str = None, end_time: str = None) -> list:
    """
    Queries SQL database (SceneCaption, Vehicle, Face, Track) for keyword matches
    when Qdrant vector search is empty or unavailable.
    """
    try:
        from ..database.connection import SessionLocal
        from ..database.models import SceneCaption, Vehicle, Face, RawOCR
        from sqlalchemy import or_
        q_norm = normalize_text(query_text)
        q_words = [w for w in q_norm.split() if w not in STOPWORDS and len(w) > 1]
        if not q_words:
            q_words = [query_text.strip().lower()]

        results = []
        seen_snapshots = set()

        with SessionLocal() as db:
            # 1. Search SceneCaptions (OR matching across keywords)
            query_sc = db.query(SceneCaption)
            sc_conds = [SceneCaption.caption.ilike(f"%{w}%") for w in q_words]
            if sc_conds:
                query_sc = query_sc.filter(or_(*sc_conds))
            if start_time:
                query_sc = query_sc.filter(SceneCaption.timestamp >= start_time)
            if end_time:
                query_sc = query_sc.filter(SceneCaption.timestamp <= end_time)

            sc_list = query_sc.order_by(SceneCaption.timestamp.desc()).limit(limit).all()
            for sc in sc_list:
                snap = sc.snapshot_url or ""
                if snap and snap in seen_snapshots:
                    continue
                if snap:
                    seen_snapshots.add(snap)

                # Compute keyword overlap score
                cap_lower = (sc.caption or "").lower()
                matched_cnt = sum(1 for w in q_words if w in cap_lower)
                sc_score = min(0.98, 0.70 + (0.10 * matched_cnt))

                results.append({
                    "score": sc_score,
                    "payload": {
                        "type": "scene",
                        "camera_id": sc.camera_id,
                        "caption": sc.caption,
                        "snapshot_url": sc.snapshot_url,
                        "timestamp": sc.timestamp.isoformat() if sc.timestamp else ""
                    }
                })

            # 2. Search RawOCR for signboards, bus labels, shop text, banners
            query_ocr = db.query(RawOCR)
            ocr_conds = [RawOCR.raw_text.ilike(f"%{w}%") for w in q_words]
            if ocr_conds:
                query_ocr = query_ocr.filter(or_(*ocr_conds))
            if start_time:
                query_ocr = query_ocr.filter(RawOCR.timestamp >= start_time)
            if end_time:
                query_ocr = query_ocr.filter(RawOCR.timestamp <= end_time)

            ocr_list = query_ocr.order_by(RawOCR.timestamp.desc()).limit(limit).all()
            for o in ocr_list:
                snap = o.snapshot_url or ""
                if snap and snap in seen_snapshots:
                    continue
                if snap:
                    seen_snapshots.add(snap)

                results.append({
                    "score": 0.92,
                    "payload": {
                        "type": "scene",
                        "camera_id": o.camera_id,
                        "caption": f"OCR Detected Text: {o.raw_text}",
                        "snapshot_url": o.snapshot_url,
                        "timestamp": o.timestamp.isoformat() if o.timestamp else ""
                    }
                })

            # 3. Search Vehicles (license plate, color, vehicle_type)
            query_v = db.query(Vehicle)
            conds = []
            for w in q_words:
                conds.append(Vehicle.license_plate.ilike(f"%{w}%"))
                conds.append(Vehicle.vehicle_color.ilike(f"%{w}%"))
                conds.append(Vehicle.vehicle_type.ilike(f"%{w}%"))
            if conds:
                query_v = query_v.filter(or_(*conds))

            if start_time:
                query_v = query_v.filter(Vehicle.timestamp >= start_time)
            if end_time:
                query_v = query_v.filter(Vehicle.timestamp <= end_time)

            v_list = query_v.order_by(Vehicle.timestamp.desc()).limit(limit).all()
            for v in v_list:
                results.append({
                    "score": 0.95 if any(w in (v.license_plate or "").lower() for w in q_words) else 0.85,
                    "payload": {
                        "type": "vehicle",
                        "camera_id": v.camera_id or "cam_1",
                        "license_plate": v.license_plate,
                        "vehicle_type": v.vehicle_type,
                        "vehicle_color": v.vehicle_color,
                        "identity_uuid": f"VEHICLE_{v.license_plate}" if v.license_plate else f"track_{v.track_uuid}",
                        "track_uuid": v.track_uuid,
                        "snapshot_url": v.snapshot_url or (f"/api/v1/playback/snapshot/{v.track_uuid}" if v.track_uuid else None),
                        "timestamp": v.timestamp.isoformat() if v.timestamp else "",
                        "bbox": json.loads(v.bbox) if (v.bbox and v.bbox != "[]") else None
                    }
                })

            # 3. Search GlobalIdentities & Faces by person name / label / identity_uuid
            from ..database.models import GlobalIdentity, Face, Track
            gi_list = db.query(GlobalIdentity).filter(
                or_(*[GlobalIdentity.name.ilike(f"%{w}%") for w in q_words] + [GlobalIdentity.identity_uuid.ilike(f"%{w}%") for w in q_words])
            ).limit(limit).all()

            for gi in gi_list:
                matched_faces = db.query(Face).filter(
                    or_(Face.label == gi.identity_uuid, Face.label == gi.name)
                ).order_by(Face.timestamp.desc()).limit(5).all()

                for f in matched_faces:
                    tr = db.query(Track).filter(Track.track_uuid == f.track_uuid).first() if f.track_uuid else None
                    cam_id = tr.camera_id if tr else "cam_1"
                    results.append({
                        "score": 0.98,
                        "payload": {
                            "type": "face",
                            "camera_id": cam_id,
                            "label": gi.name,
                            "identity_uuid": gi.identity_uuid,
                            "caption": f"Identified Person: {gi.name} ({gi.identity_uuid})",
                            "snapshot_url": f"/api/v1/watchlist/{gi.identity_uuid}/snapshot",
                            "timestamp": f.timestamp.isoformat() if f.timestamp else ""
                        }
                    })

        return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]
    except Exception as e:
        logger.warning(f"SQL search fallback note: {e}")
        return []


def perform_semantic_search(query_text: str, limit: int = 10, start_time: str = None, end_time: str = None) -> list:
    """
    Translates search query to real semantic embeddings via SentenceTransformer & OpenCLIP,
    querying Qdrant for matching scene captions and visual person crop features.

    Falls back to SQL database and in-memory keyword overlap if Qdrant is empty or unreachable.
    """
    _seed_demo_vector_db()

    scene_query_vec = get_text_embedding(query_text)
    is_production = os.getenv("APP_ENV") == "production"
    query_filter = _build_qdrant_time_filter(start_time, end_time)

    try:
        from .qdrant_utils import qdrant_client_with_timeout

        # Only invoke OpenCLIP text encoder when query targets person attributes
        q_lower = query_text.lower()
        needs_person_clip = any(w in q_lower for w in ["person", "man", "woman", "shirt", "jacket", "dress", "guy", "lady", "boy", "girl", "wearing", "clothes", "backpack", "bag"])

        clip_query_vec = None
        if needs_person_clip:
            try:
                from ..ai.person.person_attribute_engine import get_clip_text_embedding
                clip_query_vec = get_clip_text_embedding(query_text)
            except Exception as clip_e:
                logger.debug(f"OpenCLIP text embedding skipped: {clip_e}")

        qd_results = []
        with qdrant_client_with_timeout(1.5) as client:
            # 1. Search scene captions
            try:
                scene_res = client.query_points(
                    collection_name="vms_embeddings",
                    query=scene_query_vec,
                    using="scene",
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                ).points
                if scene_res:
                    qd_results.extend(scene_res)
            except Exception as e:
                logger.debug(f"Qdrant scene query note: {e}")

            # 2. Search OpenCLIP person crops (only when clip_query_vec is computed)
            if clip_query_vec:
                try:
                    crop_res = client.query_points(
                        collection_name="vms_embeddings",
                        query=clip_query_vec,
                        using="person_crop",
                        query_filter=query_filter,
                        limit=limit,
                        with_payload=True
                    ).points
                    if crop_res:
                        qd_results.extend(crop_res)
                except Exception as e:
                    logger.debug(f"Qdrant person_crop query note: {e}")

        # BUG-05 FIX: detect vehicle-class keywords in the query so we can
        # penalise results whose yolo_class contradicts the requested class.
        _VEHICLE_CLASSES = {
            "car", "motorcycle", "truck", "bus", "bicycle",
            "van", "suv", "rickshaw", "scooter", "moped"
        }
        q_lower_norm = normalize_text(query_text)
        query_vehicle_class = next(
            (c for c in _VEHICLE_CLASSES if c in q_lower_norm.split()), None
        )

        MIN_SCENE_SCORE = 0.55

        if qd_results:
            results = []
            seen_snapshots = set()
            snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))

            for r in qd_results:
                base_score = float(r.score)
                p_type = r.payload.get("type", "")

                snap_url = r.payload.get("snapshot_url") or ""
                cam_id = r.payload.get("camera_id") or ""
                snap_id = snap_url.split("/")[-1] if snap_url else ""

                if snap_id:
                    if snap_id in seen_snapshots:
                        continue
                    seen_snapshots.add(snap_id)

                    # Direct O(1) stat check on candidate file only
                    has_file = (
                        os.path.isfile(os.path.join(snap_dir, f"{snap_id}.jpg")) or 
                        os.path.isfile(os.path.join(snap_dir, snap_id)) or 
                        os.path.isfile(os.path.join(snap_dir, f"full_{snap_id}.jpg"))
                    )
                    if not has_file:
                        continue

                text_to_compare = " ".join(filter(None, [
                    str(r.payload.get("caption") or ""),
                    str(r.payload.get("upper_color") or ""),
                    str(r.payload.get("lower_color") or ""),
                    str(r.payload.get("vehicle_type") or ""),
                    str(r.payload.get("vehicle_color") or ""),
                    str(r.payload.get("license_plate") or "")
                ])).strip()

                boost_or_penalty = _keyword_boost(query_text, text_to_compare)
                score = base_score + boost_or_penalty

                # Drop scene results below the minimum similarity threshold
                if score < MIN_SCENE_SCORE:
                    continue

                score = min(score, 0.99)  # Cap score at 0.99 so UI doesn't exceed 99%

                payload = dict(r.payload)
                if snap_id and os.path.isfile(os.path.join(snap_dir, f"full_{snap_id}.jpg")):
                    payload["full_snapshot_url"] = f"/api/v1/playback/snapshot/full_{snap_id}"
                elif snap_url:
                    payload["full_snapshot_url"] = snap_url

                results.append({"score": score, "payload": payload})

            if results:
                return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]
    except Exception as e:
        if is_production:
            raise RuntimeError(f"FATAL: Qdrant search failed in production: {e}") from e
        logger.warning("Qdrant unavailable, falling back to SQL/in-memory: %s", e)

    # Fallback 1: SQL database text matches
    sql_matches = _sql_text_matches(query_text, limit, start_time, end_time)
    if sql_matches:
        return sql_matches

    # Fallback 2: local in-memory word-overlap search on seeded demo records
    return _local_text_matches(query_text, limit, start_time, end_time)


def perform_face_search(face_embedding: list, limit: int = 10, start_time: str = None, end_time: str = None) -> list:
    """
    Performs vector similarity search matching query face embedding against indexed faces,
    optionally filtered by time range. Enforces a strict minimum similarity threshold (>= 0.45).
    """
    is_production = os.getenv("APP_ENV") == "production"
    query_filter = _build_qdrant_time_filter(start_time, end_time)
    MIN_FACE_SCORE = 0.45

    try:
        from .qdrant_utils import qdrant_client_with_timeout
        with qdrant_client_with_timeout(2.0) as client:
            qd_results = client.query_points(
                collection_name="vms_embeddings",
                query=face_embedding,
                using="face",
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            ).points

        if qd_results:
            valid_results = [
                {"score": float(r.score), "payload": r.payload} 
                for r in qd_results 
                if float(r.score) >= MIN_FACE_SCORE
            ]
            if valid_results:
                return sorted(valid_results, key=lambda x: x["score"], reverse=True)
    except Exception as e:
        if is_production:
            raise RuntimeError(f"FATAL: Qdrant face search failed in production: {e}") from e
        logger.warning("Qdrant unavailable for face search, falling back to in-memory: %s", e)

    # Fallback: in-memory cosine similarity over locally held face vectors
    matches = []
    for item in model_manager.vector_db:
        if item["payload"].get("type") == "face":
            item_ts = item["payload"].get("timestamp")
            if item_ts:
                if start_time and item_ts < start_time:
                    continue
                if end_time and item_ts > end_time:
                    continue
            sim = cosine_similarity(face_embedding, item["vector"])
            if sim >= MIN_FACE_SCORE:
                matches.append({"score": sim, "payload": item["payload"]})

    matches = sorted(matches, key=lambda x: x["score"], reverse=True)
    return matches[:limit]


def perform_vehicle_search(vehicle_embedding: list, limit: int = 10, start_time: str = None, end_time: str = None) -> list:
    """
    Performs vector similarity search matching query vehicle embedding (576-dim)
    against indexed vehicles, optionally filtered by time range.
    """
    is_production = os.getenv("APP_ENV") == "production"
    query_filter = _build_qdrant_time_filter(start_time, end_time)
    MIN_VEHICLE_SCORE = 0.40

    try:
        from .qdrant_utils import qdrant_client_with_timeout
        with qdrant_client_with_timeout(2.0) as client:
            qd_results = client.query_points(
                collection_name="vms_embeddings",
                query=vehicle_embedding,
                using="vehicle",
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            ).points

        if qd_results:
            valid_results = [
                {"score": float(r.score), "payload": r.payload}
                for r in qd_results
                if float(r.score) >= MIN_VEHICLE_SCORE
            ]
            if valid_results:
                return sorted(valid_results, key=lambda x: x["score"], reverse=True)
    except Exception as e:
        if is_production:
            raise RuntimeError(f"FATAL: Qdrant vehicle search failed in production: {e}") from e
        logger.warning("Qdrant unavailable for vehicle search, falling back to in-memory: %s", e)

    # Fallback: in-memory cosine similarity
    matches = []
    for item in model_manager.vector_db:
        if item["payload"].get("type") == "vehicle":
            item_ts = item["payload"].get("timestamp")
            if item_ts:
                if start_time and item_ts < start_time:
                    continue
                if end_time and item_ts > end_time:
                    continue
            sim = cosine_similarity(vehicle_embedding, item["vector"])
            if sim >= MIN_VEHICLE_SCORE:
                matches.append({"score": sim, "payload": item["payload"]})

    matches = sorted(matches, key=lambda x: x["score"], reverse=True)
    return matches[:limit]