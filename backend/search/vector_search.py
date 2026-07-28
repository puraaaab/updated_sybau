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


def perform_semantic_search(query_text: str, limit: int = 10, start_time: str = None, end_time: str = None) -> list:
    """
    Translates search query to a real semantic embedding via SentenceTransformer,
    then queries Qdrant for cosine-similar results, optionally filtered by time range.

    Falls back to in-memory keyword overlap only if Qdrant is unreachable.
    """
    _seed_demo_vector_db()

    query_vector = get_text_embedding(query_text)
    is_production = os.getenv("APP_ENV") == "production"
    query_filter = _build_qdrant_time_filter(start_time, end_time)

    try:
        from .qdrant_utils import qdrant_client_with_timeout
        with qdrant_client_with_timeout(5.0) as client:
            qd_results = client.query_points(
                collection_name="vms_embeddings",
                query=query_vector,
                using="scene",
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            ).points

        if qd_results:
            results = []
            snap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "storage", "snapshots"))
            for r in qd_results:
                snap_url = r.payload.get("snapshot_url") or ""
                if snap_url:
                    snap_id = snap_url.split("/")[-1]
                    snap_path = os.path.join(snap_dir, f"{snap_id}.jpg")
                    raw_path = os.path.join(snap_dir, snap_id)
                    if not (os.path.exists(snap_path) or os.path.exists(raw_path)):
                        continue  # Skip records whose snapshot image files no longer exist on disk

                score = r.score
                text_to_compare = " ".join(filter(None, [
                    str(r.payload.get("caption") or ""),
                    str(r.payload.get("vehicle_type") or ""),
                    str(r.payload.get("vehicle_color") or ""),
                    str(r.payload.get("license_plate") or "")
                ])).strip()
                score += _keyword_boost(query_text, text_to_compare)
                score = min(score, 0.99)  # Cap score at 0.99 so UI doesn't exceed 99%
                results.append({"score": score, "payload": r.payload})

            return sorted(results, key=lambda x: x["score"], reverse=True)
    except Exception as e:
        if is_production:
            raise RuntimeError(f"FATAL: Qdrant search failed in production: {e}") from e
        logger.warning("Qdrant unavailable, falling back to in-memory: %s", e)

    # Fallback: local in-memory word-overlap search on seeded demo records
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