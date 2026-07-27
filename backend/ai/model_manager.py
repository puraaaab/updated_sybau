import os
import json
import warnings
import torch
import threading
from ..config.service import get_models

# Suppress huggingface_hub deprecation noise (resume_download FutureWarning)
# that appears in the log on every startup. It's harmless — library internals.
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub")


class MockYOLO:
    def __init__(self):
        print("MockYOLO initialized (Demo Mode)")

    def track(self, source, persist=True, tracker="bytetrack.yaml", verbose=False,
              classes=None, conf=None, **kwargs):
        """
        Mirrors the real ultralytics.YOLO.track() signature (including
        classes= and conf=, plus **kwargs for forward-compat) so callers
        can pass the same arguments in demo mode without a TypeError.
        classes/conf are applied to the fixed mock detections below so
        demo mode behaves consistently with the filtering callers expect.
        """
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
    def readtext(self, img_crop):
        return [([[0, 0], [100, 0], [100, 20], [0, 20]], "ABC1234", 0.95)]


class MockFlorence:
    def generate(self, *args, **kwargs):
        return "A person walking near the counter with a black bag."


class ModelManager:
    def __init__(self):
        self._models = {}
        self.vector_db = []
        self._lock = threading.Lock()

    def _is_demo(self):
        cfg = get_models()
        return cfg.get("demo_mode", False)

    def get_yolo(self):
        with self._lock:
            if "yolo" in self._models:
                return self._models["yolo"]

            if self._is_demo():
                self._models["yolo"] = MockYOLO()
                return self._models["yolo"]

            from ultralytics import YOLO
            cfg = get_models().get("yolo", {})
            model_path = cfg.get("model_path", "yolo26m.pt")
            device_cfg = cfg.get("device", "cuda")
            device = device_cfg if device_cfg != "cuda" or torch.cuda.is_available() else "cpu"
            print(f"Loading YOLO model {model_path} on {device}...")
            model = YOLO(model_path)
            model.to(device)
            self._models["yolo"] = model
            return model

    def get_ocr(self):
        with self._lock:
            if "ocr" in self._models:
                return self._models["ocr"]

            if self._is_demo():
                self._models["ocr"] = MockOCR()
                return self._models["ocr"]

            cfg = get_models().get("vehicle", {})
            engine_choice = cfg.get("ocr_engine", "paddleocr").lower()

            if engine_choice == "paddleocr":
                try:
                    from paddleocr import PaddleOCR
                    print("Loading PaddleOCR ultra-fast license plate engine...")
                    reader = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)
                    self._models["ocr"] = ("paddleocr", reader)
                    return self._models["ocr"]
                except Exception as e:
                    print(f"PaddleOCR note ({e}), falling back to EasyOCR...")

            import easyocr
            print("Loading EasyOCR reader...")
            reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available())
            self._models["ocr"] = ("easyocr", reader)
            return self._models["ocr"]

    def get_florence(self):
        with self._lock:
            if "florence" in self._models:
                return self._models["florence"]

            if self._is_demo():
                self._models["florence"] = (MockFlorence(), None)
                return self._models["florence"]

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

            cfg = get_models().get("florence", {})
            model_id = cfg.get("model_id", "microsoft/Florence-2-large")
            device = cfg.get("device", "cuda" if torch.cuda.is_available() else "cpu")
            print(f"Loading Florence-2 model {model_id} on {device}...")
            processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
            dtype = torch.float16 if device == "cuda" else torch.float32
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                trust_remote_code=True,
                torch_dtype=dtype
            ).to(device)
            model.eval()
            self._models["florence"] = (model, processor)
            return self._models["florence"]

    get_paddle_ocr = get_ocr


# Global Instance
model_manager = ModelManager()