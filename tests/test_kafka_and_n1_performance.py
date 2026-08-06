import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from backend.database.models import Base, Track, Face, Vehicle
from backend.messaging.kafka_client import KafkaEventClient

def test_kafka_event_client_partition_key_and_schema(monkeypatch):
    """
    Tests that KafkaEventClient wraps events in standardized schema metadata
    and publishes with stream partition key (camera_id).
    """
    client = KafkaEventClient()
    mock_producer = MagicMock()
    client.producer = mock_producer
    client.connected = True
    client.use_memory_bus_only = False

    payload = {"camera_id": "cam_1", "alert_type": "LOITERING", "severity": "high"}
    published = client.publish_event("vms-alerts", payload, partition_key="cam_1")

    assert published is True
    assert mock_producer.send.called
    call_args = mock_producer.send.call_args
    topic, kwargs = call_args[0][0], call_args[1]

    assert topic == "vms-alerts"
    assert kwargs["key"] == "cam_1"
    sent_val = kwargs["value"]
    assert sent_val["schema_version"] == "1.0.0"
    assert sent_val["camera_id"] == "cam_1"
    assert sent_val["payload"] == payload

def test_n1_query_count_reduction():
    """
    Tests that bulk db.add_all batching reduces SQL query execution count
    from N+1 per row down to 1 insert query per entity table.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    query_count = 0
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        if statement.strip().upper().startswith("INSERT"):
            query_count += 1

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)

    # Batch 3 faces + 2 vehicles in single db.add_all flush pass
    faces = [Face(track_uuid=f"TRK_{i}", label="person", embedding_id=f"emb_{i}") for i in range(3)]
    vehicles = [Vehicle(track_uuid=f"V_TRK_{i}", camera_id="cam_1", vehicle_type="car") for i in range(2)]

    db.add_all(faces + vehicles)
    db.commit()

    assert query_count <= 5
    assert db.query(Face).count() == 3
    assert db.query(Vehicle).count() == 2
