from sqlalchemy.orm import Session
from ..database.connection import SessionLocal
from ..database.models import Camera

class CameraStateMachine:
    CONNECTING = "connecting"
    ONLINE = "online"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"

    @staticmethod
    def update_state(camera_id: str, new_state: str):
        """
        Thread-safe status update for camera connection state.
        Writes status to database for real-time dashboard health metrics.
        """
        db: Session = SessionLocal()
        try:
            cam = db.query(Camera).filter(Camera.id == camera_id).first()
            if cam:
                cam.status = new_state
                db.commit()
                print(f"[CameraState] Camera {camera_id} transitioned to: {new_state.upper()}")
        except Exception as e:
            print(f"[CameraState] Error updating camera state for {camera_id}: {e}")
        finally:
            db.close()
