import os
import json
import warnings
import time
import torch
import threading
import logging
from ..config.service import get_models

logger = logging.getLogger(__name__) 

# Suppress huggingface_hub deprecation noise (resume_download FutureWarning)
# that appears in the log on every startup. It's harmless — library internals.
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub")


class MockYOLO:
    def __init__(self):
        print("MockYOLO initialized (Demo Mode)")

    def track(self, source, persist=True, tracker="bytetrack.yaml", verbose=False,
              classes=None, conf=None, **kwargs):
        class MockBox:
            def __init__(self, xyxy, id, cls, conf):
                self.xyxy = torch.tensor([xyxy])
                self.id = torch.tensor([id]) if id is not None else None
                self.cls = torch.tensor([cls])
                self.conf = torch.tensor([conf])

        class MockBoxList:
            def __init__(self, boxes):
                self.boxes = boxes

            def __len__(self):
                return len(self.boxes)

            def __iter__(self):
                return iter(self.boxes)

            @property
            def xyxy(self):
                return torch.tensor([b.xyxy[0].tolist() for b in self.boxes])

            @property
            def id(self):
                return torch.tensor([b.id[0].item() if b.id is not None else -1 for b in self.boxes])

            @property
            def cls(self):
                return torch.tensor([b.cls[0].item() for b in self.boxes])

            @property
            def conf(self):
                return torch.tensor([b.conf[0].item() for b in self.boxes])

        class MockResult:
            def __init__(self, boxes):
                self.boxes = MockBoxList(boxes)

        all_boxes = [
            MockBox([100.0, 150.0, 250.0, 450.0], 1, 0, 0.92),
            MockBox([400.0, 300.0, 700.0, 550.0], 2, 2, 0.88)
        ]

        if classes is not None:
            allowed = set(classes)
            all_boxes = [b for b in all_boxes if int(b.cls.item()) in allowed]
        if conf is not None:
            all_boxes = [b for b in all_boxes if float(b.conf.item()) >= conf]

        return [MockResult(all_boxes)]


class MockOCR:
    def readtext(self, img_crop, *args, **kwargs):
        return [([[0, 0], [100, 0], [100, 20], [0, 20]], "KA51MB8811", 0.95)]


class MockFlorence:
    def generate(self, *args, **kwargs):
        return "A person walking near the counter with a black bag."


class ModelManager:
    def __init__(self):
        self._models = {}
        self.vector_db = []
        self._lock = threading.Lock()
        self._florence_lock = threading.RLock()

    def _is_demo(self):
        cfg = get_models()
        return cfg.get("demo_mode", False)

    def get_yolo(self):
        with self._lock:
            if "yolo" in self._models:
                return self._models["yolo"]

        if self._is_demo():
            mock = MockYOLO()
            with self._lock:
                self._models["yolo"] = mock
            return mock

        with self._lock:
            if "yolo" in self._models:
                return self._models["yolo"]

            from ultralytics import YOLO
            import os as _os
            cfg = get_models().get("yolo", {})
            model_path = cfg.get("model_path", "yolo26m.pt")
            if not _os.path.isabs(model_path):
                project_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
                candidate_path = _os.path.join(project_root, model_path)
                if _os.path.exists(candidate_path):
                    model_path = candidate_path
            device_cfg = cfg.get("device", "cuda")
            device = device_cfg if device_cfg != "cuda" or torch.cuda.is_available() else "cpu"
            print(f"Loading YOLO model {model_path} on {device}...", flush=True)
            model = YOLO(model_path)
            model.to(device)
            self._models["yolo"] = model
            return model

    def get_ocr(self):
        with self._lock:
            if "ocr" in self._models:
                return self._models["ocr"]

        if self._is_demo():
            mock = ("mock", MockOCR())
            with self._lock:
                self._models["ocr"] = mock
            return mock

        with self._lock:
            if "ocr" in self._models:
                return self._models["ocr"]

            cfg = get_models().get("vehicle", {})
            engine_choice = cfg.get("ocr_engine", "paddleocr").lower()

            if engine_choice == "paddleocr":
                try:
                    import numpy as _np
                    from paddleocr import PaddleOCR
                    import paddleocr as _pocr_mod
                    _pocr_ver = tuple(int(x) for x in getattr(_pocr_mod, "__version__", "2.0.0").split(".")[:2])
                    print("Loading PaddleOCR ultra-fast license plate engine...", flush=True)
                    if _pocr_ver >= (3, 0):
                        reader = PaddleOCR(use_textline_orientation=False, lang='en')
                        _probe = _np.ones((32, 128, 3), dtype=_np.uint8) * 128
                        reader.predict(_probe)
                    else:
                        reader = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)
                        _probe = _np.ones((32, 128, 3), dtype=_np.uint8) * 128
                        reader.ocr(_probe, cls=False)
                    print("PaddleOCR inference probe passed — engine is healthy.", flush=True)
                    res = ("paddleocr", reader)
                    self._models["ocr"] = res
                    return res
                except Exception as e:
                    print(f"PaddleOCR note ({e}), falling back to EasyOCR...", flush=True)

            try:
                import easyocr
                print("Loading EasyOCR reader...", flush=True)
                reader = easyocr.Reader(['en'], gpu=False)
                res = ("easyocr", reader)
                self._models["ocr"] = res
                return res
            except Exception as e:
                print(f"EasyOCR note ({e}), falling back to MockOCR...", flush=True)
                res = ("mock", MockOCR())
                self._models["ocr"] = res
                return res

    def get_florence(self):
        logger.debug(f"[FLORENCE-TRACE] get_florence() called, cached={'florence' in self._models}")
        with self._lock:
            if "florence" in self._models:
                return self._models["florence"]

        logger.info("[FLORENCE-TRACE] waiting to acquire _florence_lock...")
        with self._florence_lock:
            logger.info("[FLORENCE-TRACE] acquired _florence_lock")
            with self._lock:
                if "florence" in self._models:
                    return self._models["florence"]

            if self._is_demo():
                mock = (MockFlorence(), None)
                with self._lock:
                    self._models["florence"] = mock
                return mock

            # everything below is now INSIDE the florence_lock — only one thread
            # can ever be loading the model at a time
            from transformers import AutoProcessor, AutoModelForCausalLM
            import sys
            from unittest.mock import MagicMock
            if "flash_attn" not in sys.modules:
                mock = MagicMock()
                mock.__spec__ = MagicMock()
                sys.modules["flash_attn"] = mock
                sys.modules["flash_attn.bert_padding"] = mock
                sys.modules["flash_attn.flash_attn_interface"] = mock
                sys.modules["flash_attn.flash_attn_triton"] = mock

            try:
                import transformers.dynamic_module_utils as _dmu
                if not getattr(_dmu, "_flash_attn_patched", False):
                    _orig_ci = _dmu.check_imports
                    def _patched_ci(filename):
                        try:
                            return _orig_ci(filename)
                        except ImportError as _ie:
                            if "flash_attn" in str(_ie):
                                return []
                            raise
                    _dmu.check_imports = _patched_ci
                    _dmu._flash_attn_patched = True
            except Exception:
                pass

            cfg = get_models().get("florence", {})
            model_id = cfg.get("model_id", "microsoft/Florence-2-base")
            device = cfg.get("device", "cuda" if torch.cuda.is_available() else "cpu")
            dtype = torch.bfloat16 if (device == "cuda" and torch.cuda.is_bf16_supported()) else (torch.float16 if device == "cuda" else torch.float32)

            logger.warning(f"Loading Florence-2 model {model_id} on {device}...")
            t_load0 = time.time()

            def _load_florence_target(target_id):
                try:
                    logger.info(f"[FLORENCE-TRACE] attempting from_pretrained({target_id}, local_files_only=True)")
                    p = AutoProcessor.from_pretrained(target_id, trust_remote_code=True, local_files_only=True)
                    m = AutoModelForCausalLM.from_pretrained(target_id, trust_remote_code=True, torch_dtype=dtype, local_files_only=True).to(device)
                    return p, m
                except Exception:
                    logger.info(f"[FLORENCE-TRACE] attempting from_pretrained({target_id}, local_files_only=False)")
                    p = AutoProcessor.from_pretrained(target_id, trust_remote_code=True)
                    m = AutoModelForCausalLM.from_pretrained(target_id, trust_remote_code=True, torch_dtype=dtype).to(device)
                    return p, m

            try:
                processor, model = _load_florence_target(model_id)
            except Exception as _primary_err:
                logger.error(f"Primary Florence load ({model_id}) failed: {_primary_err}. Clearing CUDA cache and falling back to microsoft/Florence-2-base...")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                processor, model = _load_florence_target("microsoft/Florence-2-base")

            model.eval()
            res = (model, processor)
            with self._lock:
                self._models["florence"] = res
            logger.info(f"[FLORENCE-TRACE] Florence fully loaded in {time.time()-t_load0:.1f}s, device={device}, dtype={dtype}")
            logger.warning(f"Florence-2 vision model ready on {device}!")
            return res

    def is_florence_ready(self) -> bool:
        with self._lock:
            return "florence" in self._models

    get_paddle_ocr = get_ocr


# Global Instance
model_manager = ModelManager()