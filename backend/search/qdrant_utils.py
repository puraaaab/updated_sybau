import logging
import threading
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_global_qdrant_client = None
_client_lock = threading.Lock()
_collection_initialized = False

def get_qdrant_client(timeout: float = 2.0):
    """
    Returns a thread-safe singleton instance of QdrantClient.
    Initializes collections once at connection time.
    """
    global _global_qdrant_client, _collection_initialized
    if _global_qdrant_client is not None:
        return _global_qdrant_client

    with _client_lock:
        if _global_qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.http import models as qmodels

                client = QdrantClient("http://localhost:6333", timeout=timeout)
                
                # Check / initialize collection once
                if not _collection_initialized:
                    try:
                        collections = client.get_collections().collections
                        exists = any(c.name == "vms_embeddings" for c in collections)
                        if not exists:
                            client.create_collection(
                                collection_name="vms_embeddings",
                                vectors_config={
                                    "face": qmodels.VectorParams(size=512, distance=qmodels.Distance.COSINE),
                                    "scene": qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE),
                                    "vehicle": qmodels.VectorParams(size=576, distance=qmodels.Distance.COSINE)
                                }
                            )
                        _collection_initialized = True
                    except Exception as e:
                        logger.warning(f"Qdrant collection init failed: {e}")
                
                _global_qdrant_client = client
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant: {e}")
                return None

    return _global_qdrant_client


@contextmanager
def qdrant_client_with_timeout(timeout: float = 2.0):
    """
    Context manager returning the singleton Qdrant client without closing it per request.
    """
    client = get_qdrant_client(timeout=timeout)
    if client is None:
        raise RuntimeError("Qdrant client not available")
    try:
        yield client
    except Exception:
        raise
