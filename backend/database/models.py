"""
VMS Pro — SQLAlchemy ORM Models (Production Forensic VMS Architecture)
Timezone-aware IST defaults (datetime.now(_IST)).
Includes Canonical Event Contract, Parent Event Lineage, Multi-Tenancy Scoping,
Normalized Person & Vehicle Journey Events, Camera Health Logs, Baselines,
Evidence Chain of Custody, AI Skill Registry, and Event Rules.
"""

import datetime
from sqlalchemy import Column, Index, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .connection import Base

# Timezone-aware IST helper — Indian Standard Time (+05:30)
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _istnow() -> datetime.datetime:
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
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)
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
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class CanonicalEvent(Base):
    """
    Canonical Event Contract with Deduplication Key & Source Event Lineage.
    Serves as primary unified event ledger across Video, Audio, Spatial, and Fusion events.
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_uuid = Column(String, unique=True, index=True, nullable=False)
    deduplication_key = Column(String, index=True, nullable=False)
    parent_event_id = Column(String, index=True, nullable=True)
    source_event_ids_json = Column(Text, default="[]", nullable=False)  # JSON list of contributing event UUIDs
    
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    
    event_type = Column(String, index=True, nullable=False)  # e.g., restricted_area_entry, glass_break, fusion_high_risk
    source_type = Column(String, index=True, default="video")  # video, audio, fusion, health, rule
    source_component = Column(String, default="ai_pipeline")
    
    status = Column(String, default="DETECTED", index=True, nullable=False)  # DETECTED, CONFIRMED, ACTIVE, RESOLVED, DISMISSED, ARCHIVED
    severity = Column(String, default="medium", index=True, nullable=False)  # info, low, medium, high, critical
    confidence = Column(Float, default=0.95, index=True, nullable=False)
    
    track_id = Column(String, index=True, nullable=True)
    global_identity_id = Column(String, index=True, nullable=True)
    metadata_json = Column(Text, default="{}", nullable=False)  # JSON dictionary of event metadata
    
    model_name = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    inference_backend = Column(String, nullable=True)
    
    snapshot_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    evidence_refs_json = Column(Text, default="[]", nullable=False)
    
    timestamp_start = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    timestamp_end = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    is_acknowledged = Column(Boolean, default=False, index=True)

    def __init__(self, **kwargs):
        import time, uuid, json
        if "type" in kwargs and "event_type" not in kwargs:
            kwargs["event_type"] = kwargs.pop("type")
        if "timestamp" in kwargs and "timestamp_start" not in kwargs:
            ts = kwargs.pop("timestamp")
            kwargs["timestamp_start"] = ts
            kwargs["timestamp_end"] = ts
        if "message" in kwargs and "metadata_json" not in kwargs:
            kwargs["metadata_json"] = json.dumps({"message": kwargs.pop("message")})
        elif "message" in kwargs:
            kwargs.pop("message")
        if "event_uuid" not in kwargs:
            kwargs["event_uuid"] = f"EVT_{uuid.uuid4().hex[:8]}"
        if "deduplication_key" not in kwargs:
            cam = kwargs.get("camera_id", "cam")
            ev_type = kwargs.get("event_type", "alert")
            kwargs["deduplication_key"] = f"{cam}_{ev_type}_{int(time.time())}"
        super().__init__(**kwargs)

    @property
    def timestamp(self):
        return self.timestamp_start

    @property
    def type(self):
        return self.event_type


# For backward compatibility with legacy endpoints querying `Alert`


Alert = CanonicalEvent



class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    label = Column(String, nullable=False)  # person, car, etc.
    first_seen = Column(DateTime(timezone=True), default=_istnow)
    last_seen = Column(DateTime(timezone=True), default=_istnow)
    speed = Column(Float, default=0.0)      # px/s
    path_history = Column(Text, default="[]")  # JSON string of [[x,y], ...]
    last_bbox_x = Column(Float, default=0.5, nullable=False)
    last_bbox_y = Column(Float, default=0.5, nullable=False)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=True)
    embedding_id = Column(String, index=True, nullable=True)  # Qdrant UUID
    label = Column(String, default="Unknown")
    confidence = Column(Float, default=0.0, index=True)
    timestamp = Column(DateTime(timezone=True), default=_istnow)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    track_uuid = Column(String, index=True, nullable=True)
    camera_id = Column(String, index=True, nullable=True)
    license_plate = Column(String, index=True, nullable=True)
    ocr_confidence = Column(Float, default=0.0, index=True)
    vehicle_type = Column(String, default="unknown")
    vehicle_color = Column(String, default="unknown", index=True)
    snapshot_url = Column(String, nullable=True)
    bbox = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_istnow)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class RawOCR(Base):
    __tablename__ = "raw_ocr_records"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    track_uuid = Column(String, index=True, nullable=True)
    detected_text = Column(String, nullable=False, index=True)
    raw_text = Column(String, nullable=True)
    ocr_confidence = Column(Float, default=0.0, index=True)
    source_type = Column(String, default="license_plate")
    snapshot_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    type = Column(String, nullable=False)  # restricted, loitering, wrong_direction, line_crossing, etc.
    name = Column(String, nullable=True)
    points = Column(Text, nullable=False)  # JSON list of [x, y] coordinates
    direction_vector = Column(String, nullable=True)  # JSON vector for line crossing
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, unique=True, index=True, nullable=False)
    loitering_seconds = Column(Integer, default=10)
    running_speed_threshold = Column(Float, default=150.0)
    crowd_density_threshold = Column(Integer, default=5)


class CustomAlertRule(Base):
    __tablename__ = "custom_alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    prompt = Column(String, nullable=False)
    camera_id = Column(String, default="ALL", index=True)
    severity = Column(String, default="high")
    is_active = Column(Boolean, default=True)
    confidence_threshold = Column(Float, default=0.35)
    created_at = Column(DateTime(timezone=True), default=_istnow)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class GlobalIdentity(Base):
    """Primary Global Identity registry for Person & Vehicle Re-ID."""
    __tablename__ = "global_identities"

    id = Column(Integer, primary_key=True, index=True)
    identity_uuid = Column(String, unique=True, index=True, nullable=False)  # e.g. "GLOBAL_PERSON_0042"
    type = Column(String, nullable=False, index=True)  # person, vehicle
    name = Column(String, default="Unknown Identity")
    first_seen = Column(DateTime(timezone=True), default=_istnow)
    last_seen = Column(DateTime(timezone=True), default=_istnow)
    embedding_id = Column(String, index=True, nullable=True)
    snapshot_path = Column(String, nullable=True)
    attributes_json = Column(Text, default="{}", nullable=False)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class PersonJourneyEvent(Base):
    """Normalized relational table for Person Re-ID Journey events."""
    __tablename__ = "person_journey_events"

    id = Column(Integer, primary_key=True, index=True)
    global_person_id = Column(String, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    track_id = Column(String, index=True, nullable=True)
    timestamp_start = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    timestamp_end = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    confidence = Column(Float, default=0.0, index=True, nullable=False)
    embedding_ref = Column(String, nullable=True)
    transition_from_camera = Column(String, nullable=True)
    transition_to_camera = Column(String, nullable=True)
    snapshot_url = Column(String, nullable=True)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class VehicleJourneyEvent(Base):
    """Normalized relational table for Vehicle Re-ID Journey events."""
    __tablename__ = "vehicle_journey_events"

    id = Column(Integer, primary_key=True, index=True)
    global_vehicle_id = Column(String, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    track_id = Column(String, index=True, nullable=True)
    license_plate = Column(String, index=True, nullable=True)
    timestamp_start = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    timestamp_end = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    confidence = Column(Float, default=0.0, index=True, nullable=False)
    embedding_ref = Column(String, nullable=True)
    transition_from_camera = Column(String, nullable=True)
    transition_to_camera = Column(String, nullable=True)
    snapshot_url = Column(String, nullable=True)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class AudioEvent(Base):
    """Stores structured audio anomaly & classifier event telemetry."""
    __tablename__ = "audio_events"

    id = Column(Integer, primary_key=True, index=True)
    event_uuid = Column(String, unique=True, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    duration_seconds = Column(Float, default=1.0)
    event_type = Column(String, index=True, nullable=False)  # glass_break, scream, gunshot, loud_noise, etc.
    is_anomaly = Column(Boolean, default=True, index=True)
    classifier_name = Column(String, nullable=False)  # acoustic_fft_rms or yamnet_onnx
    model_name = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    confidence = Column(Float, default=0.0, index=True)
    anomaly_score = Column(Float, default=0.0)
    decibels = Column(Float, default=0.0)
    peak_frequency_hz = Column(Float, default=0.0)
    audio_features_json = Column(Text, default="{}", nullable=False)
    evidence_ref = Column(String, nullable=True)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class CameraTopology(Base):
    """Stores spatial distance and travel time constraints between camera pairs."""
    __tablename__ = "camera_topologies"

    id = Column(Integer, primary_key=True, index=True)
    from_camera_id = Column(String, index=True, nullable=False)
    to_camera_id = Column(String, index=True, nullable=False)
    min_travel_seconds = Column(Float, default=5.0)
    max_travel_seconds = Column(Float, default=1800.0)
    distance_meters = Column(Float, default=50.0)


class CameraHealthLog(Base):
    """Detailed telemetry log for camera health and tampering detection."""
    __tablename__ = "camera_health_logs"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True, nullable=False)
    status = Column(String, default="ONLINE", index=True)
    fps = Column(Float, default=0.0)
    bitrate_kbps = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    reconnect_count = Column(Integer, default=0)
    freeze_score = Column(Float, default=0.0)
    dark_score = Column(Float, default=0.0)
    blur_score = Column(Float, default=0.0)
    obscure_score = Column(Float, default=0.0)
    movement_score = Column(Float, default=0.0)


class CameraBaseline(Base):
    """Statistical hourly activity baseline per camera for anomaly calculation."""
    __tablename__ = "camera_baselines"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    hour_of_day = Column(Integer, index=True, nullable=False)  # 0 to 23
    avg_count = Column(Float, default=0.0)
    std_dev = Column(Float, default=1.0)
    min_count = Column(Integer, default=0)
    max_count = Column(Integer, default=0)
    sample_count = Column(Integer, default=0)


class Investigation(Base):
    """Records AI Investigation Copilot sessions and tool audit trail."""
    __tablename__ = "investigations"

    id = Column(Integer, primary_key=True, index=True)
    investigation_uuid = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, index=True, nullable=False)
    question = Column(Text, nullable=False)
    time_range_json = Column(Text, default="{}", nullable=False)
    camera_ids_json = Column(Text, default="[]", nullable=False)
    tool_calls_json = Column(Text, default="[]", nullable=False)
    returned_event_ids_json = Column(Text, default="[]", nullable=False)
    final_answer = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True)


class EvidenceLedger(Base):
    """Forensic evidence ledger with SHA-256 integrity and signed sidecar manifest."""
    __tablename__ = "evidence_ledger"

    id = Column(Integer, primary_key=True, index=True)
    evidence_uuid = Column(String, unique=True, index=True, nullable=False)
    camera_id = Column(String, index=True, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    sha256_hash = Column(String, nullable=False, index=True)
    manifest_signature = Column(Text, nullable=True)
    creator_username = Column(String, index=True, nullable=False)
    original_file_path = Column(String, nullable=False)
    redacted_file_path = Column(String, nullable=True)
    is_protected = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_istnow, index=True)


class EvidenceChainOfCustody(Base):
    """Append-only audit ledger for evidence access, view, download, and verification."""
    __tablename__ = "evidence_chain_of_custody"

    id = Column(Integer, primary_key=True, index=True)
    evidence_uuid = Column(String, index=True, nullable=False)
    username = Column(String, index=True, nullable=False)
    action = Column(String, index=True, nullable=False)  # CREATED, VIEWED, EXPORTED, DOWNLOADED, SHARED, VERIFIED
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True)
    reason_comment = Column(Text, nullable=True)


class AISkillRegistry(Base):
    """AI Skill Registry for dynamic per-camera skill allocation and versioning."""
    __tablename__ = "ai_skills_registry"

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    input_type = Column(String, default="frame")  # frame, audio, video
    output_schema_json = Column(Text, default="{}", nullable=False)
    hardware_req = Column(String, default="CPU")
    min_fps = Column(Float, default=1.0)
    target_fps = Column(Float, default=5.0)
    max_fps = Column(Float, default=10.0)
    is_enabled = Column(Boolean, default=True)


class CameraSkillAssignment(Base):
    """Mapping of AI skills assigned to specific cameras."""
    __tablename__ = "camera_skill_assignments"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    skill_id = Column(String, index=True, nullable=False)
    config_json = Column(Text, default="{}", nullable=False)


class EventRule(Base):
    """Dynamic multi-condition event fusion & alert rules engine."""
    __tablename__ = "event_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    conditions_json = Column(Text, nullable=False)  # JSON array of conditions
    actions_json = Column(Text, nullable=False)     # JSON array of actions (MQTT, Webhook, Email, Alert)
    severity = Column(String, default="high")
    cooldown_seconds = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    organization_id = Column(String, default="org_default", index=True, nullable=False)
    site_id = Column(String, default="site_main", index=True, nullable=False)


class AuditLog(Base):
    """Tracks all privileged actions for compliance and forensic audit trail."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)
    action = Column(String, nullable=False, index=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=True)
    query_text = Column(String, nullable=True)
    query_type = Column(String, default="semantic")
    result_count = Column(Integer, default=0)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True)


class SceneCaption(Base):
    __tablename__ = "scene_captions"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, index=True, nullable=False)
    caption = Column(Text, nullable=False)
    snapshot_url = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_istnow, index=True)
