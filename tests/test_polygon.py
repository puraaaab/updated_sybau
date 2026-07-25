import pytest
from backend.ai.behavior.restricted import is_point_in_polygon, RestrictedAreaDetector

def test_point_in_polygon_raycast():
    # Square polygon from (0.2, 0.2) to (0.8, 0.8)
    polygon = [
        {"x": 0.2, "y": 0.2},
        {"x": 0.8, "y": 0.2},
        {"x": 0.8, "y": 0.8},
        {"x": 0.2, "y": 0.8}
    ]
    
    # Point inside
    assert is_point_in_polygon(0.5, 0.5, polygon, 1.0, 1.0) is True
    
    # Point outside
    assert is_point_in_polygon(0.1, 0.5, polygon, 1.0, 1.0) is False
    assert is_point_in_polygon(0.9, 0.9, polygon, 1.0, 1.0) is False

def test_restricted_area_detector():
    detector = RestrictedAreaDetector()
    
    # Square restricted zone definition
    zones = [
      {
        "id": "restricted_zone_1",
        "name": "Server Room",
        "type": "restricted",
        "points": [
            {"x": 0.2, "y": 0.2},
            {"x": 0.8, "y": 0.2},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8}
        ]
      }
    ]
    
    # Track located inside (cx: 0.5, cy: 0.7 - bottom center inside square)
    track_inside = {
        "track_id": 4,
        "label": "person",
        "bbox": [0.4, 0.3, 0.6, 0.7] # bottom center is at (0.5, 0.7)
    }
    
    triggered, msg = detector.check(track_inside, zones, 1.0, 1.0)
    assert triggered is True
    assert "entered restricted area: Server Room" in msg
    
    # Track located outside (cx: 0.1, cy: 0.5 - bottom center outside)
    track_outside = {
        "track_id": 5,
        "label": "person",
        "bbox": [0.05, 0.2, 0.15, 0.5] # bottom center is at (0.1, 0.5)
    }
    
    triggered_outside, msg_outside = detector.check(track_outside, zones, 1.0, 1.0)
    assert triggered_outside is False
