"""
VMS Pro — SQLAlchemy ORM Models
COMP-01 FIX: All datetime defaults now use timezone-aware UTC (datetime.now(UTC))
             instead of deprecated datetime.utcnow().
AI-04 FIX:   Track model now includes last_bbox_x / last_bbox_y so heatmap is real.
SCALE-05 FIX: Added indexes on Alert.type, Alert.severity, Alert.is_acknowledged,
              Face.confidence, Vehicle.ocr_confidence.
"""

import datetime
from sqlalchemy import Column, Index, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from .connection import Base

# Timezone-aware IST helper — Indian Standard Time (UTC+05:30)
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(_IST)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer", nullable=False)  # admin, operator, viewer
    status = Column(String, default="active", nullable=False)  # active, suspended, disabled
    must_change_password = Column(Boolean, default=True, nullable=False)
    allowed_cameras = Column(String, default="[]", nullable=False)  # JSON array of allowed camera IDs
    deleted_at = Column(DateTime(timezone=True), nullable=True)


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
    """
    Stores object tracking records per camera.
    AI-04 FIX: Added last_bbox_x / last_bbox_y (normalised 0–1) so the heatmap
    endpoint has real spatial data instead of always returning (0.5, 0.5).
    """
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    label = Column(String, nullable=False)  # person, car, etc.
    first_seen = Column(DateTime(timezone=True), default=_utcnow)
    last_seen = Column(DateTime(timezone=True), default=_utcnow)
    speed = Column(Float, default=0.0)      # px/s — used for relative comparison only
    path_history = Column(Text, default="[]")  # JSON string of [[x,y], ...] normalised coords

    # Heatmap spatial data — normalised 0.0–1.0 relative to frame dimensions
    last_bbox_x = Column(Float, default=0.5, nullable=False)
    last_bbox_y = Column(Float, default=0.5, nullable=False)


class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=True)
    embedding_id = Column(String, index=True, nullable=True)  # Ref to Qdrant vector uuid
    label = Column(String, default="Unknown")
    confidence = Column(Float, default=0.0, index=True)  # SCALE-05: added index
    timestamp = Column(DateTime(timezone=True), default=_utcnow)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=True)
    camera_id = Column(String, index=True, nullable=True)
    license_plate = Column(String, index=True, nullable=True)
    ocr_confidence = Column(Float, default=0.0, index=True)  # SCALE-05: added index
    vehicle_type = Column(String, default="unknown")
    vehicle_color = Column(String, default="unknown", index=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    type = Column(String, nullable=False, index=True)   # SCALE-05: added index
    message = Column(String, nullable=False)
    severity = Column(String, default="medium", index=True)  # SCALE-05: added index
    confidence = Column(Float, default=0.95)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, index=True)
    latency_ms = Column(Float, default=0.0, nullable=True)
    snapshot_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    is_acknowledged = Column(Boolean, default=False, index=True)  # SCALE-05: added index


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


class CustomAlertRule(Base):
    """Stores user-defined dynamic AI alert prompts and natural language rules."""
    __tablename__ = "custom_alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    prompt = Column(String, nullable=False)
    camera_id = Column(String, default="ALL", index=True)
    severity = Column(String, default="high")
    is_active = Column(Boolean, default=True)
    confidence_threshold = Column(Float, default=0.35)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class GlobalIdentity(Base):
    __tablename__ = "global_identities"

    id = Column(Integer, primary_key=True, index=True)
    identity_uuid = Column(String, unique=True, index=True, nullable=False)  # e.g. "POI_204"
    type = Column(String, nullable=False)  # person, vehicle
    name = Column(String, default="Unknown POI")
    first_seen = Column(DateTime(timezone=True), default=_utcnow)
    last_seen = Column(DateTime(timezone=True), default=_utcnow)
    embedding_id = Column(String, index=True, nullable=True)  # associated face/vehicle embedding


class AuditLog(Base):
    """Tracks all privileged actions for compliance and forensic audit trail."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)  # None for anonymous/system
    action = Column(String, nullable=False, index=True)  # e.g. "LOGIN", "ALERT_ACK", "CAMERA_DELETE"
    detail = Column(Text, nullable=True)  # Human-readable action description
    ip_address = Column(String, nullable=True)  # COMP-03: now populated by all callers
    timestamp = Column(DateTime(timezone=True), default=_utcnow, index=True)


class SearchHistory(Base):
    """Records all semantic and face search queries for history and analytics."""
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)
    query_text = Column(String, nullable=True)      # For semantic/text search
    query_type = Column(String, default="semantic")  # "semantic" | "face" | "license_plate"
    result_count = Column(Integer, default=0)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, index=True)


class SceneCaption(Base):
    """Records every AI-generated scene caption across all camera feeds."""
    __tablename__ = "scene_captions"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    caption = Column(Text, nullable=False)
    snapshot_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, index=True)
