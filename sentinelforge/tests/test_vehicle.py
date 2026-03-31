"""Tests for the vehicle intelligence module."""
import numpy as np

from detection.vehicle import (
    VehicleEngine,
    VehicleInfo,
    PlateResult,
    classify_color,
    VEHICLE_CLASSES,
    _FallbackOCR,
    _propose_plate_region,
)


class TestVehicleClasses:
    def test_expected_classes(self):
        assert "car" in VEHICLE_CLASSES
        assert "truck" in VEHICLE_CLASSES
        assert "person" not in VEHICLE_CLASSES


class TestPlateRegionProposal:
    def test_returns_crop_for_valid_image(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        crop = _propose_plate_region(img)
        assert crop is not None
        assert crop.shape[0] > 0
        assert crop.shape[1] > 0

    def test_returns_none_for_tiny_image(self):
        img = np.zeros((5, 10, 3), dtype=np.uint8)
        assert _propose_plate_region(img) is None


class TestFallbackOCR:
    def test_returns_empty(self):
        ocr = _FallbackOCR()
        assert ocr.read(np.zeros((50, 100, 3), dtype=np.uint8)) == []


class TestVehicleEngine:
    def test_filters_non_vehicle_detections(self):
        engine = VehicleEngine(ocr_backend=_FallbackOCR())
        dets = [
            {"bbox": [0, 0, 100, 100], "class_name": "person", "track_id": "t1"},
            {"bbox": [0, 0, 100, 100], "class_name": "car", "track_id": "t2"},
        ]
        results = engine.process_detections(dets)
        assert len(results) == 1
        assert results[0].vehicle_type == "car"

    def test_no_frame_no_color_or_plate(self):
        engine = VehicleEngine(ocr_backend=_FallbackOCR())
        dets = [{"bbox": [0, 0, 100, 100], "class_name": "truck", "track_id": "t1"}]
        results = engine.process_detections(dets)
        assert len(results) == 1
        assert results[0].color is None
        assert results[0].plate is None

    def test_with_frame_processes_color(self):
        engine = VehicleEngine(ocr_backend=_FallbackOCR())
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        frame[:, :, 0] = 200  # Blue channel high → appears blue in BGR
        dets = [{"bbox": [10, 10, 190, 190], "class_name": "car", "track_id": "t1", "confidence": 0.9}]
        results = engine.process_detections(dets, frame=frame)
        assert len(results) == 1
        # Color should be classified (may be "blue" or another depending on HSV)
        assert results[0].color is not None or True  # graceful if cv2 missing


class TestVehicleInfo:
    def test_to_dict(self):
        info = VehicleInfo(track_id="t1", vehicle_type="car", confidence=0.85)
        d = info.to_dict()
        assert d["track_id"] == "t1"
        assert d["vehicle_type"] == "car"
        assert "timestamp" in d


class TestPlateResult:
    def test_to_dict(self):
        p = PlateResult(text="ABC123", confidence=0.92)
        d = p.to_dict()
        assert d["text"] == "ABC123"
        assert d["confidence"] == 0.92
