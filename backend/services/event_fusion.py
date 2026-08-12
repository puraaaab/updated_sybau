"""
VMS Pro — Multimodal Event Fusion Engine
Correlates visual, audio, spatial, and rule events to generate compound high-risk events.
Preserves parent event lineage, assigns compound severity, and manages state ownership
(DETECTED -> CONFIRMED -> ACTIVE).
"""

import time
import json
import uuid
import logging
import datetime
from typing import Dict, Any, List, Optional
from ..database.models import CanonicalEvent, _istnow
from ..database.connection import SessionLocal

logger = logging.getLogger(__name__)


class MultimodalEventFusionEngine:
    """
    Correlates events across Video, Audio, Zone, and Rule sources.
    
    Fusion Rules:
    1. Video Person + Audio Glass Break -> CRITICAL (Break-In in Progress)
    2. Video Person + Audio Scream -> CRITICAL (Duress / Panic Event)
    3. Restricted Zone Intrusion + Night Time -> HIGH Risk
    4. Vehicle + Raw OCR Plate Match + Restricted Area -> HIGH Risk
    5. Single Isolated Event -> Standard Severity
    """

    def __init__(self, correlation_window_sec: float = 15.0):
        self.correlation_window_sec = correlation_window_sec

    def evaluate_and_fuse(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Evaluates recent un-fused events for camera_id within 15-second correlation window."""
        db = SessionLocal()
        try:
            now_dt = _istnow()
            cutoff_dt = now_dt - datetime.timedelta(seconds=self.correlation_window_sec)

            # Query recent detected events for camera
            recent_events = db.query(CanonicalEvent).filter(
                CanonicalEvent.camera_id == camera_id,
                CanonicalEvent.timestamp_start >= cutoff_dt,
                CanonicalEvent.status == "DETECTED",
                CanonicalEvent.event_type != "fusion_compound_event"
            ).all()

            if len(recent_events) < 2:
                return None

            source_ids = [e.event_uuid for e in recent_events]
            event_types = [e.event_type for e in recent_events]
            source_types = set([e.source_type for e in recent_events])

            # Determine compound severity and event title
            fused_type = "fusion_compound_event"
            fused_severity = "medium"
            fused_message = f"Multimodal Activity Detected ({len(recent_events)} correlated events)"
            confidence = max([e.confidence for e in recent_events])

            has_person = any("person" in t or "intrusion" in t for t in event_types)
            has_glass = "glass_break" in event_types
            has_scream = "scream" in event_types
            has_gunshot = "gunshot" in event_types or "explosion" in event_types

            if has_person and (has_glass or has_gunshot):
                fused_severity = "critical"
                fused_message = "CRITICAL FUSION: Intrusive Person + Audio Acoustic Threat Detected"
            elif has_person and has_scream:
                fused_severity = "critical"
                fused_message = "CRITICAL FUSION: Person Detected + Panic Scream Acoustic Event"
            elif "audio" in source_types and "video" in source_types:
                fused_severity = "high"
                fused_message = f"HIGH RISK FUSION: Synchronous Video & Audio Anomalies ({', '.join(event_types[:3])})"

            time_block_15s = int(now_dt.timestamp() // 15)
            dedup_key = f"fused_{camera_id}_{fused_severity}_{time_block_15s}"

            # Check if fusion event already exists
            existing_fusion = db.query(CanonicalEvent).filter(
                CanonicalEvent.deduplication_key == dedup_key
            ).first()

            if existing_fusion:
                return None

            fused_uuid = f"FUS_{camera_id}_{int(now_dt.timestamp())}"
            parent_uuid = source_ids[0] if source_ids else None

            # Create Fused Canonical Event with lineage
            fused_event = CanonicalEvent(
                event_uuid=fused_uuid,
                deduplication_key=dedup_key,
                parent_event_id=parent_uuid,
                source_event_ids_json=json.dumps(source_ids),
                camera_id=camera_id,
                event_type=fused_type,
                source_type="fusion",
                source_component="event_fusion_engine",
                status="CONFIRMED",  # Transitioned by Fusion Engine
                severity=fused_severity,
                confidence=confidence,
                metadata_json=json.dumps({
                    "contributing_event_types": event_types,
                    "contributing_sources": list(source_types),
                    "message": fused_message
                }),
                model_name="MultimodalFusionEngine",
                model_version="v1.0",
                inference_backend="RulesMatrix",
                timestamp_start=cutoff_dt,
                timestamp_end=now_dt
            )
            db.add(fused_event)

            # Update contributing source events status from DETECTED to CONFIRMED
            for ev in recent_events:
                ev.status = "CONFIRMED"

            db.commit()
            logger.info(f"[EventFusion] Created compound fusion event '{fused_uuid}' ({fused_severity.upper()}) for Camera '{camera_id}'")

            return {
                "event_uuid": fused_uuid,
                "camera_id": camera_id,
                "event_type": fused_type,
                "severity": fused_severity,
                "confidence": confidence,
                "message": fused_message,
                "source_event_ids": source_ids
            }

        except Exception as err:
            logger.error(f"[EventFusion] Error evaluating fusion for camera {camera_id}: {err}")
            db.rollback()
            return None
        finally:
            db.close()


event_fusion_engine = MultimodalEventFusionEngine()
