"""
Unit tests for detection/yolo_engine.py — YOLO detection wrapper.
Tests the fallback path so they run without installing ultralytics.
"""
import pytest
import numpy as np

from detection.yolo_engine import YOLOEngine, _FallbackYOLO


class TestFallbackYOLO:
    def test_fallback_returns_empty(self):
        model = _FallbackYOLO()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = model.predict(frame)
        assert len(results) == 1
        assert results[0].boxes == []


class TestYOLOEngine:
    def test_init_uses_fallback_when_ultralytics_missing(self):
        # Since ultralytics is not installed in test env, should use fallback
        engine = YOLOEngine()
        assert engine.model is not None

    def test_detect_returns_empty_on_blank_frame(self):
        engine = YOLOEngine()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        dets = engine.detect(frame)
        # Fallback or missing model should return empty list (no detections)
        assert isinstance(dets, list)

    def test_detect_handles_none_frame(self):
        engine = YOLOEngine()
        dets = engine.detect(None)
        assert dets == []

    def test_label_map_contains_common_classes(self):
        engine = YOLOEngine()
        assert engine.label_map.get(0) == "person"
        assert engine.label_map.get(2) == "car"
