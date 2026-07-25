import os
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from backend.search.qdrant_utils import qdrant_client_with_timeout

COLLECTION = "vms_embeddings"

@pytest.fixture(scope="module")
def migrate():
    # Run migration script
    from subprocess import run, PIPE
    result = run(["python", "d:/sybau_granth/backend/scripts/qdrant_migration_576.py"], capture_output=True, text=True)
    print(result.stdout)
    yield
    # No teardown needed (fresh cutover each run)

def test_collection_dimensions(migrate):
    client = QdrantClient("http://localhost:6333", timeout=2.0)
    info = client.get_collection(COLLECTION)
    # Verify vehicle vector size is 576
    vectors = info.config.params.vectors
    veh_size = vectors["vehicle"].size if isinstance(vectors, dict) else vectors.size
    assert veh_size == 576

def test_upsert_vehicle_vector(migrate):
    import uuid
    vector_id = str(uuid.uuid4())
    vehicle_vector = [0.0] * 576
    payload = {"type": "vehicle", "identity_uuid": "TEST_ID"}
    with qdrant_client_with_timeout(2.0) as client:
        client.upsert(
            collection_name=COLLECTION,
            points=[
                qmodels.PointStruct(id=vector_id, vector={"vehicle": vehicle_vector}, payload=payload)
            ]
        )
    # Verify upsert succeeded by retrieving the point
    with qdrant_client_with_timeout(5.0) as client:
        result = client.retrieve(COLLECTION, ids=[vector_id])
        assert result[0].id == vector_id
        assert result[0].payload["type"] == "vehicle"
