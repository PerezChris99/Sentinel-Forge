"""YOLO engine behavior tests using a deterministic fake model."""

# CI execution marker: validates the consolidated Phase 14 head.

import numpy as np

import detection.yolo_engine as module


class Box:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = [np.array(xyxy, dtype=float)]
        self.conf = [conf]
        self.cls = [cls]


class Result:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeYOLO:
    def __init__(self, *_args, **_kwargs):
        pass

    def predict(self, _frame, imgsz=640):
        assert imgsz == 640
        return [Result([
            Box([1.2, 2.4, 30.9, 40.8], 0.9, 0),
            Box([5, 6, 7, 8], 0.2, 2),
            object(),
        ])]


def test_yolo_detect_filters_by_confidence_and_normalizes_boxes(monkeypatch):
    monkeypatch.setattr(module, "YOLO", FakeYOLO)
    engine = module.YOLOEngine("fake.pt")
    detections = engine.detect(np.zeros((64, 64, 3), dtype=np.uint8), conf_threshold=0.3)
    assert detections == [{
        "class_id": 0,
        "class_name": "person",
        "confidence": 0.9,
        "bbox": [1, 2, 30, 40],
    }]


def test_yolo_detect_handles_none_and_predict_failure(monkeypatch):
    monkeypatch.setattr(module, "YOLO", FakeYOLO)
    engine = module.YOLOEngine("fake.pt")
    assert engine.detect(None) == []

    class Broken(FakeYOLO):
        def predict(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    engine.model = Broken()
    assert engine.detect(np.zeros((8, 8, 3), dtype=np.uint8)) == []


def test_yolo_engine_falls_back_when_model_constructor_fails(monkeypatch):
    class BrokenCtor:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("bad model")
    monkeypatch.setattr(module, "YOLO", BrokenCtor)
    engine = module.YOLOEngine("bad.pt")
    assert engine.model is not None
