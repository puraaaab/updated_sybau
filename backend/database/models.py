import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer", nullable=False)  # admin, operator, viewer
    status = Column(String, default="active", nullable=False)  # active, suspended, disabled
    must_change_password = Column(Boolean, default=False, nullable=False)
    allowed_cameras = Column(String, default="[]", nullable=False)  # JSON array of allowed camera IDs
    deleted_at = Column(DateTime, nullable=True)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String, default="Unknown")
    stream_url = Column(String, nullable=False)
    status = Column(String, default="offline")
    width = Column(Integer, default=1920)
    height = Column(Integer, default=1080)
    latitude = Column(Float, default=21.1702)
    longitude = Column(Float, default=72.8311)


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    label = Column(String, nullable=False)  # person, car, etc.
    first_seen = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)
    speed = Column(Float, default=0.0)
    path_history = Column(Text, default="[]")  # JSON string of coords


class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=True)
    embedding_id = Column(String, index=True, nullable=True)  # Ref to Qdrant vector uuid
    label = Column(String, default="Unknown")
    confidence = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=True)
    camera_id = Column(String, index=True, nullable=True)
    license_plate = Column(String, index=True, nullable=True)
    ocr_confidence = Column(Float, default=0.0)
    vehicle_type = Column(String, default="unknown")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    type = Column(String, nullable=False)  # loitering, restricted, wrong_direction, crowd, running, abandoned
    message = Column(String, nullable=False)
    severity = Column(String, default="medium")  # low, medium, high
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    snapshot_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    is_acknowledged = Column(Boolean, default=False)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    type = Column(String, nullable=False)  # restricted, loitering, wrong_direction, etc.
    name = Column(String, nullable=True)
    points = Column(Text, nullable=False)  # JSON list of [x, y] coordinates
    direction_vector = Column(String, nullable=True)  # JSON list of vector coords for wrong-direction


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, unique=True, index=True, nullable=False)
    loitering_seconds = Column(Integer, default=10)
    running_speed_threshold = Column(Float, default=150.0)
    crowd_density_threshold = Column(Integer, default=5)


class GlobalIdentity(Base):
    __tablename__ = "global_identities"

    id = Column(Integer, primary_key=True, index=True)
    identity_uuid = Column(String, unique=True, index=True, nullable=False)  # e.g. "POI_204"
    type = Column(String, nullable=False)  # person, vehicle
    name = Column(String, default="Unknown POI")
    first_seen = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)
    embedding_id = Column(String, index=True, nullable=True)  # associated face/vehicle embedding


class AuditLog(Base):
    """Tracks all privileged actions for compliance and forensic audit trail."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)  # None for anonymous/system
    action = Column(String, nullable=False)  # e.g. "LOGIN", "ALERT_ACK", "CAMERA_DELETE"
    detail = Column(Text, nullable=True)  # Human-readable action description
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class SearchHistory(Base):
    """Records all semantic and face search queries for history and analytics."""
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)
    query_text = Column(String, nullable=True)     # For semantic/text search
    query_type = Column(String, default="semantic")  # "semantic" | "face" | "license_plate"
    result_count = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
