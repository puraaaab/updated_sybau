import hashlib
import logging
import threading

import numpy as np

from ...config.service import get_models

logger = logging.getLogger(__name__)

# We'll default to 384-dimensional vectors (standard for MiniLM models)
EMBEDDING_DIM = 384

_sentence_transformer_model = None
_model_lock = threading.Lock()


def _stable_seed(text: str) -> int:
    """
    Deterministic seed derived from text, stable across process restarts.
    Python's built-in hash() is randomized per-process (PYTHONHASHSEED) and
    must NOT be used here — it would make "stable" mock embeddings differ
    every time the app restarts, breaking matching between an indexing run
    and a later search run.
    """
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return int(digest, 16) % 4294967295


def _mock_embedding(text: str) -> list:
    # Use a local RandomState instead of np.random.seed(), which mutates
    # GLOBAL numpy random state — that would race with any other code
    # using np.random concurrently and isn't safe to call from multiple
    # threads.
    rng = np.random.default_rng(_stable_seed(text))
    vec = rng.normal(0, 1, EMBEDDING_DIM)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def get_text_embedding(text: str):
    """
    Generates a 384-dimensional vector embedding for the input text.
    """
    global _sentence_transformer_model
    cfg = get_models()
    demo_mode = cfg.get("demo_mode", False)

    if demo_mode:
        # Stable mock embedding seeded by a deterministic hash of the text,
        # so that matching search queries yield closer vector similarities
        # — including across separate process runs.
        return _mock_embedding(text)

    try:
        if _sentence_transformer_model is None:
            with _model_lock:
                # Re-check inside the lock in case another thread loaded
                # it while we were waiting.
                if _sentence_transformer_model is None:
                    from sentence_transformers import SentenceTransformer
                    logger.info("Loading SentenceTransformer model (all-MiniLM-L6-v2)...")
                    _sentence_transformer_model = SentenceTransformer("all-MiniLM-L6-v2")

        embedding = _sentence_transformer_model.encode(text)
        return embedding.tolist()
    except Exception:
        logger.exception("Error loading SentenceTransformer. Falling back to hash seed simulation.")
        return _mock_embedding(text)