import time
import pytest
from backend.ai.behavior.behavior_engine import BehaviorEngine

def test_alert_cooldown_deduplication():
    engine = BehaviorEngine(default_cooldown_seconds=2.0)

    # First trigger for track_id 101 MUST be emitted
    emit1 = engine._should_emit_alert(101, "loitering", "Zone 1", cooldown_seconds=2.0)
    assert emit1 is True

    # Immediate second trigger for track_id 101 MUST be suppressed (cooldown active)
    emit2 = engine._should_emit_alert(101, "loitering", "Zone 1", cooldown_seconds=2.0)
    assert emit2 is False

    # Immediate trigger for a DIFFERENT track_id MUST be emitted
    emit_other_track = engine._should_emit_alert(102, "loitering", "Zone 1", cooldown_seconds=2.0)
    assert emit_other_track is True

    # Wait for cooldown to expire
    time.sleep(2.1)

    # After cooldown, trigger for track_id 101 MUST be emitted again
    emit3 = engine._should_emit_alert(101, "loitering", "Zone 1", cooldown_seconds=2.0)
    assert emit3 is True
