import pytest
import torch
import numpy as np


def test_yolo_uses_configured_confidence(monkeypatch):
    from backend.ai.detection import yolo

    captured = {}

    class Boxes:
        xyxy = torch.tensor([[1.0, 2.0, 3.0, 4.0]])
        id = torch.tensor([1.0])
        cls = torch.tensor([0.0])
        conf = torch.tensor([0.33])

        def __len__(self):
            return 1

    class Result:
        boxes = Boxes()

    class Model:
        def track(self, source, **kwargs):
            captured.update(kwargs)
            return [Result()]
        def predict(self, source, **kwargs):
            captured.update(kwargs)
            return [Result()]

    monkeypatch.setattr(yolo.model_manager, "get_yolo", lambda: Model())
    monkeypatch.setattr(yolo, "get_models", lambda: {"yolo": {"confidence": 0.25}})

    detections = yolo.detect_and_track(np.zeros((10, 10, 3), dtype=np.uint8))

    assert captured["conf"] == 0.25
    assert detections[0]["confidence"] == pytest.approx(0.33)
