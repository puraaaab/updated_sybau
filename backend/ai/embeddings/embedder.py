import hashlib
import logging
import threading

import numpy as np

from ...config.service import get_models

logger = logging.getLogger(__name__)

# Default vector dimension for BAAI/bge-large-en-v1.5 (1024d)
EMBEDDING_DIM = 1024

_sentence_transformer_model = None
_model_lock = threading.Lock()


def _stable_seed(text: str) -> int:
    """
    Deterministic seed derived from text, stable across process restarts.
    """
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return int(digest, 16) % 4294967295


def _mock_embedding(text: str, dim: int = EMBEDDING_DIM) -> list:
    rng = np.random.default_rng(_stable_seed(text))
    vec = rng.normal(0, 1, dim)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


_embedding_cache = {}
_cache_lock_dict = threading.Lock()

def get_text_embedding(text: str):
    """
    Generates a high-precision vector embedding for the input text using configured SentenceTransformer model.
    """
    global _sentence_transformer_model, EMBEDDING_DIM
    cfg = get_models()
    demo_mode = cfg.get("demo_mode", False)

    if not text:
        return [0.0] * EMBEDDING_DIM

    with _cache_lock_dict:
        if text in _embedding_cache:
            cached_vec = _embedding_cache[text]
            if len(cached_vec) == EMBEDDING_DIM:
                return cached_vec
            else:
                del _embedding_cache[text]

    if demo_mode:
        vec = _mock_embedding(text, EMBEDDING_DIM)
    else:
        try:
            if _sentence_transformer_model is None:
                with _model_lock:
                    if _sentence_transformer_model is None:
                        model_name = cfg.get("embeddings", {}).get("model_name", "BAAI/bge-large-en-v1.5")
                        device = cfg.get("embeddings", {}).get("device", "cpu")
                        logger.info(f"Loading SentenceTransformer text embedder ({model_name}) on {device}...")
                        
                        st_class = None
                        for _retry in range(3):
                            try:
                                from sentence_transformers import SentenceTransformer
                                st_class = SentenceTransformer
                                break
                            except ImportError:
                                import time as _t
                                _t.sleep(0.5)

                        if st_class is None:
                            from sentence_transformers import SentenceTransformer
                            st_class = SentenceTransformer

                        _sentence_transformer_model = st_class(model_name, device=device)
                        if device == "cuda" and hasattr(_sentence_transformer_model, "half"):
                            try:
                                _sentence_transformer_model.half()
                            except Exception:
                                pass
                        EMBEDDING_DIM = _sentence_transformer_model.get_sentence_embedding_dimension() or 1024

            import torch
            with torch.inference_mode():
                embedding = _sentence_transformer_model.encode(text, show_progress_bar=False)
            vec = embedding.tolist()
        except Exception:
            logger.exception("Error loading SentenceTransformer. Falling back to hash seed simulation.")
            vec = _mock_embedding(text, EMBEDDING_DIM)

    with _cache_lock_dict:
        if len(_embedding_cache) > 2000:
            _embedding_cache.clear()
        _embedding_cache[text] = vec

    return vec