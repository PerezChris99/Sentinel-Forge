"""
Unit tests for DetectionPipeline in detection/engine.py.
These tests mock the face detection step to avoid heavy CV dependencies.
"""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np

# Patch face_recognition before import so DetectionEngine can load
with patch.dict("sys.modules", {"face_recognition": MagicMock()}):
    from detection.engine import DetectionEngine, DetectionPipeline


class TestDetectionPipeline:
    @pytest.fixture
    def mock_face_engine(self):
        engine = MagicMock(spec=DetectionEngine)
        engine.detect_and_process.return_value = []
        return engine

    def test_process_frame_returns_dict_structure(self, mock_face_engine):
        pipeline = DetectionPipeline(face_engine=mock_face_engine)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = pipeline.process_frame(frame, "cam-01")

        assert "detections" in result
        assert "face_events" in result
        assert "tracks" in result
        assert isinstance(result["detections"], list)
        assert isinstance(result["tracks"], list)

    def test_yolo_fallback_runs_without_error(self, mock_face_engine):
        pipeline = DetectionPipeline(face_engine=mock_face_engine)
        # Fallback YOLO should not raise
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = pipeline.process_frame(frame, "cam-02")
        # Detections may be empty (fallback) but should not raise
        assert result is not None

    def test_face_engine_called(self, mock_face_engine):
        pipeline = DetectionPipeline(face_engine=mock_face_engine)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        pipeline.process_frame(frame, "cam-03")
        mock_face_engine.detect_and_process.assert_called_once()
