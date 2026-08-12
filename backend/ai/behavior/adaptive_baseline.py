"""
VMS Pro — Adaptive Behavioral Baseline Engine
Tracks historical hourly occupant and vehicle count distributions per camera.
Calculates statistical mean and standard deviation to detect ANOMALOUS_ACTIVITY.
"""

import json
import datetime
import logging
import numpy as np

from typing import Dict, Any, Optional
from ...database.models import CameraBaseline, CanonicalEvent, _istnow
from ...database.connection import SessionLocal

logger = logging.getLogger(__name__)


class AdaptiveBaselineEngine:
    """Per-camera adaptive behavioral baseline tracker."""

    def __init__(self, z_score_threshold: float = 3.0, min_samples: int = 5):
        self.z_score_threshold = z_score_threshold
        self.min_samples = min_samples

    def record_and_evaluate(self, camera_id: str, current_count: int) -> Optional[Dict[str, Any]]:
        now_dt = _istnow()
        hour = now_dt.hour

        db = SessionLocal()
        try:
            baseline = db.query(CameraBaseline).filter(
                CameraBaseline.camera_id == camera_id,
                CameraBaseline.hour_of_day == hour
            ).first()

            if not baseline:
                baseline = CameraBaseline(
                    camera_id=camera_id,
                    hour_of_day=hour,
                    avg_count=float(current_count),
                    std_dev=1.0,
                    min_count=current_count,
                    max_count=current_count,
                    sample_count=1
                )
                db.add(baseline)
                db.commit()
                return None

            # Calculate z-score if sufficient sample count exists
            z_score = 0.0
            is_anomalous = False
            if baseline.sample_count >= self.min_samples:
                std = max(1.0, baseline.std_dev)
                z_score = float((current_count - baseline.avg_count) / std)
                if z_score >= self.z_score_threshold:
                    is_anomalous = True

            # Update running statistical mean and std dev
            n = baseline.sample_count + 1
            new_avg = baseline.avg_count + (current_count - baseline.avg_count) / float(n)
            new_var = ((baseline.std_dev ** 2) * baseline.sample_count + (current_count - baseline.avg_count) * (current_count - new_avg)) / float(n)
            new_std = float(np.sqrt(max(1.0, new_var)))

            baseline.avg_count = round(new_avg, 2)
            baseline.std_dev = round(new_std, 2)
            baseline.min_count = min(baseline.min_count, current_count)
            baseline.max_count = max(baseline.max_count, current_count)
            baseline.sample_count = n

            anom_payload = None
            if is_anomalous:
                ev_uuid = f"ANOM_{camera_id}_{int(now_dt.timestamp())}"
                dedup_key = f"{camera_id}_anomalous_activity_{hour}_{int(now_dt.timestamp() // 60)}"

                msg_text = f"Anomalous Occupancy: {current_count} detected (normal for hour {hour:02d}:00 is {baseline.avg_count:.1f} ± {baseline.std_dev:.1f})"
                canon_ev = CanonicalEvent(
                    event_uuid=ev_uuid,
                    deduplication_key=dedup_key,
                    camera_id=camera_id,
                    event_type="ANOMALOUS_ACTIVITY",
                    source_type="behavior",
                    source_component="adaptive_baseline",
                    status="DETECTED",
                    metadata_json=json.dumps({"message": msg_text, "z_score": z_score}),
                    severity="high" if z_score > 4.0 else "medium",
                    confidence=round(min(0.99, z_score / 5.0), 2),
                    model_name="AdaptiveBaselineEngine",
                    model_version="v1.0",
                    inference_backend="ZScoreStatistics",
                    timestamp_start=now_dt,
                    timestamp_end=now_dt
                )

                db.add(canon_ev)
                anom_payload = {
                    "event_type": "ANOMALOUS_ACTIVITY",
                    "camera_id": camera_id,
                    "current_count": current_count,
                    "baseline_avg": baseline.avg_count,
                    "z_score": round(z_score, 2)
                }

            db.commit()
            return anom_payload

        except Exception as e:
            logger.error(f"[AdaptiveBaseline] Error for camera {camera_id}: {e}")
            db.rollback()
            return None
        finally:
            db.close()


adaptive_baseline_engine = AdaptiveBaselineEngine()
