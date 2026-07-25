#!/usr/bin/env python
"""Qdrant migration script
Drops the existing `vms_embeddings` collection (if it exists) and recreates it
with a 576‑dimensional vector for `vehicle` embeddings.
Data is not preserved – a clean cutover as per user request.
"""
import os
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

def migrate_collection():
    client = QdrantClient("http://localhost:6333", timeout=2.0)
    collection_name = "vms_embeddings"
    # Drop if exists
    try:
        client.delete_collection(collection_name)
        print(f"Deleted existing collection '{collection_name}'.")
    except Exception:
        print(f"Collection '{collection_name}' did not exist or could not be deleted.")
    # Create new collection with desired vector config
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "face": qmodels.VectorParams(size=512, distance=qmodels.Distance.COSINE),
            "scene": qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE),
            "vehicle": qmodels.VectorParams(size=576, distance=qmodels.Distance.COSINE),
        },
    )
    print(f"Created collection '{collection_name}' with vehicle vector size 576.")

if __name__ == "__main__":
    migrate_collection()
