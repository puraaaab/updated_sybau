import logging
import os

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
    "automobile": "car", "vehicle": "car", "sedan": "car", "suv": "car",
    "footpath": "sidewalk", "pavement": "sidewalk",
    "handbag": "bag", "backpack": "bag", "purse": "bag"
}


def normalize_text(text: str) -> str:
    text = text.lower().replace("-", " ").strip()
    for old, new in _TEXT_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def _keyword_boost(query_text: str, candidate_text: str) -> float:
    """Word-overlap + phrase-match boost used to nudge raw vector scores."""
    q_text_norm = normalize_text(query_text)
    q_words = {w for w in q_text_norm.split() if w not in STOPWORDS}
    if not q_words:
        return 0.0

    text_comp_norm = normalize_text(candidate_text)
    c_words = {w for w in text_comp_norm.split() if w not in STOPWORDS}

    boost = 0.0
    intersect = q_words.intersection(c_words)
    if intersect:
        boost += float(len(intersect) / len(q_words)) * 0.4

    if q_text_norm and q_text_norm in text_comp_norm:
        boost += 0.5

    return boost


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
        from ..database.models import SceneCaption, Vehicle, Face
        q_norm = normalize_text(query_text)
        q_words = [w for w in q_norm.split() if w not in STOPWORDS and len(w) > 1]
        if not q_words:
            q_words = [query_text.strip().lower()]

        results = []
        seen_snapshots = set()

        with SessionLocal() as db:
            # 1. Search SceneCaptions
            query_sc = db.query(SceneCaption)
            for word in q_words[:3]:
                query_sc = query_sc.filter(SceneCaption.caption.ilike(f"%{word}%"))
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

                results.append({
                    "score": 0.88,
                    "payload": {
                        "type": "scene",
                        "camera_id": sc.camera_id,
                        "caption": sc.caption,
                        "snapshot_url": sc.snapshot_url,
                        "timestamp": sc.timestamp.isoformat() if sc.timestamp else ""
                    }
                })

            # 2. Search Vehicles (license plate, color, vehicle_type)
            from sqlalchemy import or_
            query_v = db.query(Vehicle)
            conds = []
            for word in q_words[:3]:
                conds.append(Vehicle.license_plate.ilike(f"%{word}%"))
                conds.append(Vehicle.vehicle_color.ilike(f"%{word}%"))
                conds.append(Vehicle.vehicle_type.ilike(f"%{word}%"))
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
                        "snapshot_url": f"/api/v1/playback/snapshot/veh_{v.id}",
                        "timestamp": v.timestamp.isoformat() if v.timestamp else ""
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
        from ..ai.person.person_attribute_engine import get_clip_text_embedding
        clip_query_vec = get_clip_text_embedding(query_text)

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

            # 2. Search OpenCLIP person crops
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

            # 3. Search Vehicle Re-ID / attribute vectors
            try:
                veh_res = client.query_points(
                    collection_name="vms_embeddings",
                    query=scene_query_vec,
                    using="vehicle",
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                ).points
                if veh_res:
                    qd_results.extend(veh_res)
            except Exception as e:
                logger.debug(f"Qdrant vehicle query note: {e}")

        if qd_results:
            results = []
            seen_snapshots = set()
            snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))

            for r in qd_results:
                snap_url = r.payload.get("snapshot_url") or ""
                if snap_url:
                    if snap_url in seen_snapshots:
                        continue
                    seen_snapshots.add(snap_url)

                    snap_id = snap_url.split("/")[-1]
                    snap_path = os.path.join(snap_dir, f"{snap_id}.jpg")
                    raw_path = os.path.join(snap_dir, snap_id)
                    if not (os.path.exists(snap_path) or os.path.exists(raw_path)):
                        continue  # Skip records whose snapshot image files no longer exist on disk

                score = float(r.score)
                text_to_compare = " ".join(filter(None, [
                    str(r.payload.get("caption") or ""),
                    str(r.payload.get("upper_color") or ""),
                    str(r.payload.get("lower_color") or ""),
                    str(r.payload.get("vehicle_type") or ""),
                    str(r.payload.get("vehicle_color") or ""),
                    str(r.payload.get("license_plate") or "")
                ])).strip()
                score += _keyword_boost(query_text, text_to_compare)
                score = min(score, 0.99)  # Cap score at 0.99 so UI doesn't exceed 99%
                results.append({"score": score, "payload": r.payload})

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
    optionally filtered by time range.
    """
    is_production = os.getenv("APP_ENV") == "production"
    query_filter = _build_qdrant_time_filter(start_time, end_time)

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
            return [{"score": r.score, "payload": r.payload} for r in qd_results]
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
            matches.append({"score": sim, "payload": item["payload"]})

    matches = sorted(matches, key=lambda x: x["score"], reverse=True)
    return matches[:limit]