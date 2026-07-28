import logging
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)


class DownstreamRouter:
    def __init__(self, websocket_manager: Any, secondary_task_queue: asyncio.Queue, max_queue_size: int = 100):
        """
        Routes batch tracking results simultaneously to high-speed WebSockets and secondary AI models.
        
        Args:
            websocket_manager: The FastAPI WebSocket broadcast manager instance.
            secondary_task_queue: An asyncio.Queue hooked into Florence-2 / PaddleOCR consumers.
            max_queue_size: Hard cap on the secondary queue to prevent unconsumed crops from ballooning RAM.
        """
        self.ws_manager = websocket_manager
        self.secondary_queue = secondary_task_queue
        self.max_queue_size = max_queue_size
        
        # High-value targets for deep structural processing on Indian streets
        self.DEEP_PROCESSING_CLASSES = {
            "person", "car", "truck", "motorcycle", "bus", "bicycle", "auto_rickshaw",
            "rickshaw", "tuktuk", "scooter", "moped", "van", "suv", "vehicle", "three_wheeler", "cow"
        }

    async def route_batch_results(self, batch_detections: Dict[str, List[Dict[str, Any]]], original_frames: Dict[str, np.ndarray]):
        """
        Executes dual-path routing over websocket managers and async processing loops.
        """
        # --- PATH A: Zero-Latency WebSocket Broadcast ---
        # Fire and forget tracking arrays to the UI immediately
        try:
            asyncio.create_task(self._broadcast_to_websockets(batch_detections))
        except Exception:
            logger.exception("Failed to initialize WebSocket broadcast task.")

        # --- PATH B: Async Queue Injection for Secondary Deep Models ---
        for stream_id, detections in batch_detections.items():
            frame = original_frames.get(stream_id)
            if frame is None or not detections:
                continue

            for det in detections:
                class_name = det.get("class_name")
                
                # Filter for entities requiring text extraction or semantic captioning
                if class_name in self.DEEP_PROCESSING_CLASSES:
                    # Guard memory allocations: if consumer falls behind, drop frames gracefully (load shedding)
                    if self.secondary_queue.qsize() >= self.max_queue_size:
                        logger.warning(
                            f"⚠️ Secondary AI Queue Full ({self.secondary_queue.qsize()}/{self.max_queue_size}). "
                            f"Dropping downstream tasks for track_id {det['track_id']} to save VRAM."
                        )
                        break  # Stop processing this stream's deeper data to clear buffer pressure
                    
                    bbox = det.get("bbox")  # [x1, y1, x2, y2]
                    try:
                        # Extract the crop coordinates safely using numpy constraints
                        h, w, _ = frame.shape
                        x1, y1, x2, y2 = map(int, bbox)
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        
                        crop = frame[y1:y2, x1:x2].copy()
                        
                        if crop.size == 0:
                            continue

                        payload = {
                            "stream_id": stream_id,
                            "track_id": det["track_id"],
                            "class_name": class_name,
                            "confidence": det["confidence"],
                            "crop": crop
                        }
                        
                        # Non-blocking injection into the secondary worker task queue
                        self.secondary_queue.put_nowait(payload)
                        
                    except Exception:
                        logger.exception(f"Failed to safely extract frame crop for track_id {det.get('track_id')}")

    async def _broadcast_to_websockets(self, batch_detections: Dict[str, List[Dict[str, Any]]]):
        """
        Handles explicit serialization delivery to active camera consumer connections.
        """
        for stream_id, detections in batch_detections.items():
            # Standardize payload structure for frontend UI overlays
            message = {
                "type": "tracking_update",
                "stream_id": stream_id,
                "data": detections
            }
            try:
                # Assuming your websocket manager has a broadcast_to_stream method
                await self.ws_manager.broadcast_to_stream(stream_id, message)
            except AttributeError:
                # Fallback template if your manager uses a different broadcast name
                pass
            except Exception:
                logger.error(f"WebSocket delivery failed for stream {stream_id}")
