def is_point_in_polygon(
    x: float,
    y: float,
    polygon: list,
    frame_width: float = 1920.0,
    frame_height: float = 1080.0,
) -> bool:
    """
    Ray-casting algorithm to determine if point (x, y) is inside a polygon.

    Zone points in configs/zones.json are stored as NORMALIZED coordinates
    (0.0–1.0 relative to frame size).  Bounding-box coordinates from the
    detector are raw PIXEL values.  This function normalizes the test point
    before comparison so both systems are consistent.
    """
    n = len(polygon)
    inside = False
    if n < 3:
        return False

    # Normalize the test point to the same 0-1 space as the zone polygons
    nx = x / frame_width
    ny = y / frame_height

    p1x, p1y = polygon[0]["x"], polygon[0]["y"]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]["x"], polygon[i % n]["y"]
        if ny > min(p1y, p2y):
            if ny <= max(p1y, p2y):
                if nx <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (ny - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or nx <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

class RestrictedAreaDetector:
    def check(self, track_info: dict, zones: list, frame_width: float = 1920.0, frame_height: float = 1080.0) -> tuple:
        """
        Checks if the object resides inside a restricted polygon.
        Zone points are normalized (0-1); bbox coords are pixels.
        Returns: (triggered: bool, message: str)
        """
        bbox = track_info["bbox"]
        # Use bottom-center (feet location for persons, wheels for vehicles)
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = bbox[3]

        for zone in zones:
            if zone["type"] == "restricted":
                points = zone["points"]
                if is_point_in_polygon(cx, cy, points, frame_width, frame_height):
                    msg = (
                        f"{track_info['label'].capitalize()} "
                        f"(ID {track_info['track_id']}) "
                        f"entered restricted area: {zone['name']}"
                    )
                    return True, msg
        return False, ""
