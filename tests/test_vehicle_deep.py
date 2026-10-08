"""Vehicle intelligence unit tests without external OCR engines."""

from datetime import datetime

import numpy as np

from detection.vehicle import PlateResult, VehicleEngine, VehicleInfo, _FallbackOCR, _propose_plate_region, classify_color


class FakeOCR:
    def __init__(self, results):
        self.results = results
        self.received = None

    def read(self, image):
        self.received = image
        return self.results


def test_plate_and_vehicle_serialization():
    plate = PlateResult("UAX123A", 0.91, bbox=[1, 2, 3, 4], region="UG")
    assert plate.to_dict()["text"] == "UAX123A"
    ts = datetime(2026, 1, 1)
    info = VehicleInfo("t1", "car", plate=plate, timestamp=ts, confidence=0.8)
    assert info.to_dict()["timestamp"].startswith("2026-01-01")


def test_plate_region_rejects_tiny_crop_and_proposes_valid_region():
    assert _propose_plate_region(np.zeros((10, 20, 3), dtype=np.uint8)) is None
    crop = _propose_plate_region(np.zeros((100, 200, 3), dtype=np.uint8))
    assert crop.shape == (40, 160, 3)


def test_fallback_ocr_is_safe():
    assert _FallbackOCR().read(np.zeros((10, 10, 3), dtype=np.uint8)) == []


def test_vehicle_engine_filters_non_vehicle_and_reads_high_confidence_plate():
    ocr = FakeOCR([("bad!", 0.99), ("UAX123A", 0.91)])
    engine = VehicleEngine(ocr, plate_region="US")
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    results = engine.process_detections(
        [
            {"class_name": "person", "bbox": [0, 0, 50, 50]},
            {"class_name": "car", "track_id": "t1", "confidence": 0.88, "bbox": [0, 0, 200, 100]},
        ],
        frame,
    )
    assert len(results) == 1
    assert results[0].plate.text == "UAX123A"
    assert ocr.received is not None


def test_vehicle_engine_uses_high_confidence_fallback_for_unmatched_text():
    engine = VehicleEngine(FakeOCR([("UNUSUAL", 0.8)]), plate_region="US")
    result = engine.process_detections(
        [{"class_name": "truck", "bbox": [0, 0, 100, 100]}],
        np.zeros((100, 100, 3), dtype=np.uint8),
    )[0]
    assert result.plate.text == "UNUSUAL"


def test_vehicle_engine_rejects_low_confidence_unmatched_text():
    engine = VehicleEngine(FakeOCR([("bad!", 0.4)]), plate_region="US")
    result = engine.process_detections(
        [{"class_name": "bus", "bbox": [0, 0, 100, 100]}],
        np.zeros((100, 100, 3), dtype=np.uint8),
    )[0]
    assert result.plate is None


def test_vehicle_engine_handles_invalid_bbox_and_no_frame():
    engine = VehicleEngine(FakeOCR([]))
    result = engine.process_detections(
        [{"class_name": "car", "bbox": [20, 20, 10, 10]}],
        frame=None,
    )[0]
    assert result.plate is None
    assert classify_color(np.zeros((2, 2, 3), dtype=np.uint8)) in {"unknown", "black"}
