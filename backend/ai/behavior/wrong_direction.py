def ccw(A, B, C):
    return (C["y"] - A["y"]) * (B["x"] - A["x"]) > (B["y"] - A["y"]) * (C["x"] - A["x"])

def intersect(A, B, C, D):
    """
    Checks if line segment AB and segment CD intersect.
    A, B are end-points of the line.
    C, D are start and end positions of the moving object.
    """
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

class WrongDirectionDetector:
    def check(self, track_info: dict, zones: list) -> tuple:
        """
        Determines if a moving track crosses a direction line in the wrong direction.
        Returns: (triggered: bool, message: str)
        """
        path = track_info.get("path", [])
        if len(path) < 2:
            return False, ""
            
        # Get last movement segment: C (previous position) to D (current position)
        C = {"x": path[-2][0], "y": path[-2][1]}
        D = {"x": path[-1][0], "y": path[-1][1]}
        
        # Movement vector V
        vx = D["x"] - C["x"]
        vy = D["y"] - C["y"]
        
        for zone in zones:
            if zone["type"] == "entry_exit":
                points = zone["points"]
                if len(points) < 2:
                    continue
                    
                def _to_dict(pt):
                    if isinstance(pt, dict):
                        return pt
                    return {"x": float(pt[0]), "y": float(pt[1])}

                A = _to_dict(points[0])
                B = _to_dict(points[1])
                
                # Check segment intersection
                if intersect(A, B, C, D):
                    # Check direction. allowed_dir = zone['direction'] (dx, dy)
                    allowed_dir = zone.get("direction", {"x": 0.0, "y": 0.0})
                    # Dot product V . U
                    dot_product = vx * allowed_dir.get("x", 0.0) + vy * allowed_dir.get("y", 0.0)
                    
                    # If dot product is negative, motion is opposite to allowed direction
                    if dot_product < 0:
                        msg = f"{track_info['label'].capitalize()} (ID {track_info['track_id']}) crossed boundary '{zone['name']}' in WRONG direction"
                        return True, msg
                        
        return False, ""
