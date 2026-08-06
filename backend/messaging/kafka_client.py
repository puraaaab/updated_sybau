import json
import os
import uuid
import datetime
import logging

logger = logging.getLogger(__name__)

class MemoryEventBus:
    """In-memory fallback queue for websocket-based alert delivery when Kafka is offline."""
    def __init__(self):
        self.subscribers = []

    def subscribe(self, callback):
        self.subscribers.append(callback)

    def publish(self, topic, data):
        for sub in self.subscribers:
            try:
                sub(topic, data)
            except Exception as e:
                logger.debug(f"Error in pubsub subscription: {e}")

memory_bus = MemoryEventBus()

class KafkaEventClient:
    def __init__(self):
        self.producer = None
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.use_memory_bus_only = os.getenv("USE_MEMORY_BUS_ONLY", "false").lower() == "true"
        self.connected = False

        if self.use_memory_bus_only:
            logger.info("[KafkaEventClient] USE_MEMORY_BUS_ONLY=true — running in local memory event bus mode.")
            return

        try:
            from kafka import KafkaProducer
            print(f"Connecting to Kafka broker at {self.bootstrap_servers}...")
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                key_serializer=lambda k: k.encode('utf-8') if isinstance(k, str) else k,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                request_timeout_ms=2000,
                max_block_ms=2000
            )
            self.connected = True
            print("Kafka Producer connected successfully.")
        except Exception as e:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError(f"FATAL: Kafka connection failed in production: {e}") from e
            logger.info(f"Kafka unavailable ({e}). Falling back to internal MemoryEventBus.")

    def publish_event(self, topic: str, data: dict, partition_key: str = None):
        # Format payload with standardized event schema
        schema_data = {
            "schema_version": "1.0.0",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "camera_id": data.get("camera_id", "system"),
            "payload": data
        }

        memory_bus.publish(topic, schema_data)

        if self.use_memory_bus_only:
            return True

        is_production = os.getenv("APP_ENV") == "production"
        key = partition_key or data.get("camera_id", "default")

        if self.connected and self.producer:
            try:
                self.producer.send(topic, key=key, value=schema_data)
                return True
            except Exception as e:
                self.connected = False
                if is_production:
                    raise RuntimeError(f"Failed to publish event to Kafka in production: {e}") from e
                logger.debug(f"Kafka publish note: {e}")
        else:
            if is_production:
                raise RuntimeError("Failed to publish event to Kafka in production: Kafka Producer is not connected.")
        return False

# Global instance
event_client = KafkaEventClient()
