import logging
import os
import threading
import queue
import time
import uuid as _uuid_mod
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_global_qdrant_client = None
_client_lock = threading.Lock()

_qdrant_batch_queue = queue.Queue(maxsize=10000)
_batch_thread = None
_batch_running = False


def _qdrant_base_url() -> str:
    host = os.getenv("QDRANT_HOST", "localhost")
    port = os.getenv("QDRANT_PORT", "6333")
    if "://" in host:
        return host
    return f"http://{host}:{port}"

def get_qdrant_client(timeout: float = 10.0):
    """
    Returns a thread-safe singleton instance of QdrantClient.
    Initializes collections once at connection time.
    """
    global _global_qdrant_client
    if _global_qdrant_client is not None:
        return _global_qdrant_client

    with _client_lock:
        if _global_qdrant_client is None:
            for attempt in range(3):
                try:
                    from qdrant_client import QdrantClient
                    from qdrant_client.http import models as qmodels

                    client = QdrantClient(_qdrant_base_url(), timeout=10.0)

                    try:
                        collections = client.get_collections().collections
                        exists = any(c.name == "vms_embeddings" for c in collections)
                        should_recreate = False

                        if exists:
                            info = client.get_collection("vms_embeddings")
                            params = info.config.params.vectors
                            if hasattr(params, "get"):
                                scene_size = params.get("scene").size if params.get("scene") else 0
                            elif isinstance(params, dict):
                                scene_size = params["scene"].size if "scene" in params else 0
                            else:
                                scene_size = getattr(params, "scene", None).size if hasattr(params, "scene") else 0

                            if scene_size != 1024:
                                logger.info(f"Recreating Qdrant collection 'vms_embeddings' (migrating scene vector size {scene_size} -> 1024)...")
                                client.delete_collection("vms_embeddings")
                                should_recreate = True

                        if not exists or should_recreate:
                            client.create_collection(
                                collection_name="vms_embeddings",
                                vectors_config={
                                    "face": qmodels.VectorParams(size=512, distance=qmodels.Distance.COSINE),
                                    "scene": qmodels.VectorParams(size=1024, distance=qmodels.Distance.COSINE),
                                    "vehicle": qmodels.VectorParams(size=576, distance=qmodels.Distance.COSINE),
                                    "person_crop": qmodels.VectorParams(size=768, distance=qmodels.Distance.COSINE)
                                }
                            )
                            logger.info("Created Qdrant collection 'vms_embeddings' successfully.")
                    except Exception as e:
                        logger.warning(f"Qdrant collection init check note: {e}")

                    _global_qdrant_client = client
                    break
                except Exception as e:
                    logger.warning(f"Failed to connect to Qdrant (attempt {attempt+1}/3): {e}")
                    if attempt < 2:
                        time.sleep(2)

    _ensure_batch_worker_started()
    return _global_qdrant_client


@contextmanager
def qdrant_client_with_timeout(timeout: float = 10.0):
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


def enqueue_qdrant_point(vector_id: str, vector: list, payload: dict):
    """
    Non-blocking submission of a vector point into the background batch upsert queue.
    """
    if vector is None:
        return

    p_type = payload.get("type") if isinstance(payload, dict) else None
    if p_type == "person_crop":
        vec_name = "person_crop"
    elif p_type == "face" or (len(vector) == 512 and p_type != "person_crop"):
        vec_name = "face"
    elif p_type == "vehicle" or len(vector) == 576:
        vec_name = "vehicle"
    else:
        vec_name = "scene"

    try:
        qdrant_id = str(_uuid_mod.UUID(vector_id))
    except (ValueError, AttributeError):
        qdrant_id = str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_DNS, vector_id))

    try:
        _qdrant_batch_queue.put_nowait((qdrant_id, vec_name, vector, payload))
        _ensure_batch_worker_started()
    except queue.Full:
        logger.warning("Qdrant batch queue full; dropping point to prevent backpressure.")


def _ensure_batch_worker_started():
    global _batch_thread, _batch_running
    if not _batch_running:
        with _client_lock:
            if not _batch_running:
                _batch_running = True
                _batch_thread = threading.Thread(target=_qdrant_batch_worker, daemon=True, name="QdrantBatchWorker")
                _batch_thread.start()


def _qdrant_batch_worker():
    """
    Background worker thread that drains _qdrant_batch_queue and sends bulk upserts to Qdrant.
    This eliminates per-point HTTP overhead and socket exhaustion.
    """
    from qdrant_client.http import models as qmodels

    logger.info("Qdrant background batch worker thread active.")
    while _batch_running:
        batch = []
        try:
            # Get first item blocking up to 0.5s
            item = _qdrant_batch_queue.get(timeout=0.5)
            batch.append(item)

            # Drain up to 99 more items immediately if available
            while len(batch) < 100:
                try:
                    item = _qdrant_batch_queue.get_nowait()
                    batch.append(item)
                except queue.Empty:
                    break
        except queue.Empty:
            continue

        if not batch:
            continue

        client = get_qdrant_client()
        if not client:
            continue

        points = [
            qmodels.PointStruct(
                id=qid,
                vector={vname: vec},
                payload=p
            )
            for (qid, vname, vec, p) in batch
        ]

        try:
            client.upsert(
                collection_name="vms_embeddings",
                points=points
            )
        except Exception as e:
            logger.warning(f"Qdrant batch upsert error ({len(batch)} points): {e}")
