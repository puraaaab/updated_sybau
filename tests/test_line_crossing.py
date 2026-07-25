import pytest
from backend.ai.behavior.wrong_direction import intersect, WrongDirectionDetector

def test_line_segment_intersection():
    # Segment AB: (0.5, 0.0) to (0.5, 1.0) - vertical gate line
    A = {"x": 0.5, "y": 0.0}
    B = {"x": 0.5, "y": 1.0}
    
    # Segment CD: object crossing from left to right: (0.4, 0.5) to (0.6, 0.5)
    C = {"x": 0.4, "y": 0.5}
    D = {"x": 0.6, "y": 0.5}
    
    assert intersect(A, B, C, D) is True
    
    # Segment EF: object moving parallel, not crossing: (0.3, 0.5) to (0.3, 0.8)
    E = {"x": 0.3, "y": 0.5}
    F = {"x": 0.3, "y": 0.8}
    
    assert intersect(A, B, E, F) is False

def test_wrong_direction_alert_trigger():
    detector = WrongDirectionDetector()
    
    # Setup mock track history moving left-to-right: from (0.4, 0.5) to (0.6, 0.5)
    track_info = {
        "track_id": 9,
        "label": "person",
        "path": [[0.4, 0.5], [0.6, 0.5]]
    }
    
    # Gate definition: Vertical line at x=0.5. Allowed direction is left-to-right (dx: 1.0, dy: 0.0)
    zones_allowed = [
      {
        "id": "gate_1",
        "name": "Front Door",
        "type": "entry_exit",
        "points": [{"x": 0.5, "y": 0.0}, {"x": 0.5, "y": 1.0}],
        "direction": {"x": 1.0, "y": 0.0}
      }
    ]
    
    # Moving left-to-right (same as allowed vector) -> should NOT trigger wrong direction
    triggered, msg = detector.check(track_info, zones_allowed)
    assert triggered is False
    
    # Setup mock track history moving right-to-left: from (0.6, 0.5) to (0.4, 0.5)
    track_info_wrong = {
        "track_id": 9,
        "label": "person",
        "path": [[0.6, 0.5], [0.4, 0.5]]
    }
    
    # Moving opposite to allowed vector -> should trigger wrong direction alert
    triggered_wrong, msg_wrong = detector.check(track_info_wrong, zones_allowed)
    assert triggered_wrong is True
    assert "crossed boundary 'Front Door' in WRONG direction" in msg_wrong
