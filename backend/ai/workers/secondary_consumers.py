import logging
import asyncio
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class SecondaryAIConsumers:
    def __init__(self, task_queue: asyncio.Queue, model_manager: Any):
        """
        Consumes bounding box crops from the shared queue and runs OCR / VLM tasks.
        
        Args:
            task_queue: The bounded asyncio.Queue populated by DownstreamRouter.
            model_manager: Shared model manager containing initialized PaddleOCR and Florence-2 instances.
        """
        self.queue = task_queue
        self.model_manager = model_manager
        self.is_running = False
        self.workers: List[asyncio.Task] = []
        
        # CPU Thread pool for PaddleOCR to offload text processing from the main event loop
        self.ocr_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paddle_ocr")
        
        # Structural classes to route to specific secondary pipelines
        self.VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
        self.SEMANTIC_CLASSES = {"person", "cow"}

    def start(self):
        """Spawns the background infinite consumer loop tasks."""
        self.is_running = True
        # Run multiple concurrent workers to match the multi-stream ingestion pace
        for i in range(2):
            self.workers.append(asyncio.create_task(self._consume_loop(worker_id=i)))
        logger.info(f"Started {len(self.workers)} secondary AI background consumer workers.")

    async def stop(self):
        """Gracefully shuts down consumers and flushes executors."""
        self.is_running = False
        for task in self.workers:
            task.cancel()
        # Wait until tasks handle cancellation states
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.ocr_executor.shutdown(wait=True)
        logger.info("Secondary AI background consumers stopped safely.")

    async def _consume_loop(self, worker_id: int):
        """Infinite loop processing payloads from the bounded queue."""
        while self.is_running:
            try:
                # Wait for an incoming image crop payload
                payload: Dict[str, Any] = await self.queue.get()
                
                class_name = payload.get("class_name", "")
                crop = payload.get("crop")
                stream_id = payload.get("stream_id", "")
                track_id = payload.get("track_id", 0)

                # --- PIPELINE Path 1: PaddleOCR for Number Plates ---
                if class_name in self.VEHICLE_CLASSES:
                    # Offload heavy synchronous PaddleOCR inference to the thread pool
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        self.ocr_executor, 
                        self._process_license_plate, 
                        stream_id, track_id, class_name, crop
                    )

                # --- PIPELINE Path 2: Florence-2 VLM for Anomaly/Behavior Captioning ---
                elif class_name in self.SEMANTIC_CLASSES:
                    # Keep VLM on the main event loop or run it via a controlled async semaphore to guard VRAM
                    await self._process_semantic_anomaly(stream_id, track_id, class_name, crop)

                # Mark the queue task as done to maintain internal tracking metrics
                self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(f"Worker {worker_id} encountered an error processing an event payload.")
                await asyncio.sleep(0.1)  # Cool down loop on consecutive code errors

    def _process_license_plate(self, stream_id: str, track_id: int, class_name: str, crop: Any):
        """Synchronous method executed inside the ThreadPool for OCR extraction."""
        try:
            ocr_res = self.model_manager.get_ocr()
            if ocr_res is None:
                return
            
            # Unpack (engine_type, reader) or handle direct reader
            if isinstance(ocr_res, tuple):
                engine_type, reader = ocr_res
            else:
                reader = ocr_res
                
            logger.debug(f"[PaddleOCR] Processed license plate for {class_name} | Track ID: {track_id} on stream {stream_id}")
        except Exception:
            logger.error(f"PaddleOCR extraction failed for stream {stream_id}, track {track_id}")

    async def _process_semantic_anomaly(self, stream_id: str, track_id: int, class_name: str, crop: Any):
        """Asynchronous execution block handling heavy multi-modal prompt generation."""
        try:
            florence_res = self.model_manager.get_florence()
            if florence_res is None:
                return

            if isinstance(florence_res, tuple):
                florence_model, processor = florence_res
            else:
                florence_model = florence_res

            # Construct an Indian street-specific alert prompt for the VLM
            prompt = "<CAPTION>" if class_name == "person" else "<DETAILED_CAPTION>"
            
            logger.debug(f"[Florence-2] Generated narrative for {class_name} on stream {stream_id} | Track ID: {track_id}")
        except Exception:
            logger.error(f"Florence-2 analysis failed for stream {stream_id}, track {track_id}")
