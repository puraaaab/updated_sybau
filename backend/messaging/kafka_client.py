import json
import os

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
                print(f"Error in pubsub subscription: {e}")

memory_bus = MemoryEventBus()

class KafkaEventClient:
    def __init__(self):
        self.producer = None
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.connected = False
        
        # Suppress confluent/kafka logging noise
        try:
            from kafka import KafkaProducer
            print(f"Connecting to Kafka broker at {self.bootstrap_servers}...")
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                request_timeout_ms=2000,
                max_block_ms=2000
            )
            self.connected = True
            print("Kafka Producer connected successfully.")
        except Exception as e:
            if os.getenv("APP_ENV") == "production":
                raise RuntimeError(f"FATAL: Kafka connection failed in production: {e}") from e
            print(f"Kafka unavailable: {e}. Falling back to internal MemoryEventBus.")

    def publish_event(self, topic: str, data: dict):
        # Always publish to the memory bus first (drives WebSockets in the same process)
        memory_bus.publish(topic, data)
        
        is_production = os.getenv("APP_ENV") == "production"
        
        if self.connected and self.producer:
            try:
                self.producer.send(topic, value=data)
                return True
            except Exception as e:
                self.connected = False
                if is_production:
                    raise RuntimeError(f"Failed to publish event to Kafka in production: {e}") from e
                else:
                    import logging as _logging
                    _logging.getLogger(__name__).debug(f"Kafka publish note: {e}")
        else:
            if is_production:
                raise RuntimeError("Failed to publish event to Kafka in production: Kafka Producer is not connected.")
        return False

# Global instance
event_client = KafkaEventClient()
