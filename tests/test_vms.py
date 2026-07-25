import unittest
import numpy as np

from backend.ai.behavior.wrong_direction import intersect, WrongDirectionDetector
from backend.ai.behavior.restricted import is_point_in_polygon, RestrictedAreaDetector
from backend.config import service as config_service

class TestVMSBehaviorEngine(unittest.TestCase):

    def test_line_segment_intersection(self):
        # Vertical gate line segment AB
        A = {"x": 0.5, "y": 0.0}
        B = {"x": 0.5, "y": 1.0}
        
        # Object segment CD crossing left to right
        C = {"x": 0.4, "y": 0.5}
        D = {"x": 0.6, "y": 0.5}
        self.assertTrue(intersect(A, B, C, D))
        
        # Object segment EF parallel to gate (no crossing)
        E = {"x": 0.3, "y": 0.5}
        F = {"x": 0.3, "y": 0.8}
        self.assertFalse(intersect(A, B, E, F))

    def test_wrong_direction_alert(self):
        detector = WrongDirectionDetector()
        
        # Move left-to-right: (0.4, 0.5) -> (0.6, 0.5)
        track_info = {
            "track_id": 1,
            "label": "person",
            "path": [[0.4, 0.5], [0.6, 0.5]]
        }
        
        # Vertical line x=0.5, allowed direction is left-to-right
        zones = [
          {
            "id": "gate_1",
            "name": "Entrance Gate",
            "type": "entry_exit",
            "points": [{"x": 0.5, "y": 0.0}, {"x": 0.5, "y": 1.0}],
            "direction": {"x": 1.0, "y": 0.0}
          }
        ]
        
        # Correct direction: should NOT trigger
        triggered, msg = detector.check(track_info, zones)
        self.assertFalse(triggered)
        
        # Move right-to-left: (0.6, 0.5) -> (0.4, 0.5)
        track_info_wrong = {
            "track_id": 2,
            "label": "person",
            "path": [[0.6, 0.5], [0.4, 0.5]]
        }
        
        # Wrong direction: should trigger alert
        triggered_wrong, msg_wrong = detector.check(track_info_wrong, zones)
        self.assertTrue(triggered_wrong)
        self.assertIn("crossed boundary 'Entrance Gate' in WRONG direction", msg_wrong)

    def test_point_in_polygon_raycasting(self):
        # Square from (0.2, 0.2) to (0.8, 0.8)
        polygon = [
            {"x": 0.2, "y": 0.2},
            {"x": 0.8, "y": 0.2},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8}
        ]
        
        # Center inside
        self.assertTrue(is_point_in_polygon(0.5, 0.5, polygon, 1.0, 1.0))
        # Top-left outside
        self.assertFalse(is_point_in_polygon(0.1, 0.1, polygon, 1.0, 1.0))

    def test_restricted_area_trigger(self):
        detector = RestrictedAreaDetector()
        
        zones = [
          {
            "id": "zone_1",
            "name": "Vault",
            "type": "restricted",
            "points": [
                {"x": 0.2, "y": 0.2},
                {"x": 0.8, "y": 0.2},
                {"x": 0.8, "y": 0.8},
                {"x": 0.2, "y": 0.8}
            ]
          }
        ]
        
        # Object inside restricted area
        track_inside = {
            "track_id": 10,
            "label": "person",
            "bbox": [0.4, 0.4, 0.6, 0.7] # bottom center is at (0.5, 0.7)
        }
        triggered, msg = detector.check(track_inside, zones, 1.0, 1.0)
        self.assertTrue(triggered)
        self.assertIn("entered restricted area: Vault", msg)

    def test_configurations(self):
        cams = config_service.get_cameras()
        self.assertIsInstance(cams, list)
        
        alerts = config_service.get_alerts()
        self.assertIsInstance(alerts, dict)
        self.assertIn("loitering", alerts)

if __name__ == "__main__":
    unittest.main()
