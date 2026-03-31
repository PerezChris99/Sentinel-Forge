"""
Vehicle Intelligence Module for SentinelForge.

Provides:
- License plate detection region extraction (crop from detection bbox)
- License plate OCR via EasyOCR / PaddleOCR / regex fallback
- Vehicle color classification (dominant-color extraction)
- Vehicle type classification from YOLO class labels

No heavy dependencies at import time — OCR engines loaded lazily.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)

# Common license plate regex patterns per region
_PLATE_PATTERNS = {
    "US": re.compile(r"^[A-Z0-9]{1,8}$"),
    "EU": re.compile(r"^[A-Z]{1,3}[\s\-]?\d{1,4}[\s\-]?[A-Z]{0,3}$"),
    "GENERIC": re.compile(r"^[A-Z0-9\s\-]{4,12}$"),
}

# Vehicle class labels from COCO / YOLO
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle"}

# Colour buckets (HSV-based dominant color)
_COLOR_RANGES = {
    "red":      ((0, 70, 50), (10, 255, 255)),
    "orange":   ((11, 70, 50), (25, 255, 255)),
    "yellow":   ((26, 70, 50), (35, 255, 255)),
    "green":    ((36, 70, 50), (85, 255, 255)),
    "blue":     ((86, 70, 50), (125, 255, 255)),
    "purple":   ((126, 70, 50), (155, 255, 255)),
    "white":    ((0, 0, 180), (180, 30, 255)),
    "gray":     ((0, 0, 80), (180, 30, 179)),
    "black":    ((0, 0, 0), (180, 255, 79)),
}


@dataclass
class PlateResult:
    text: str
    confidence: float
    bbox: Optional[List[int]] = None  # [x1,y1,x2,y2] within vehicle crop
    region: str = "GENERIC"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VehicleInfo:
    track_id: str
    vehicle_type: str  # car | truck | bus | …
    color: Optional[str] = None
    plate: Optional[PlateResult] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# ---- OCR backends (lazy-loaded) ---------------------------------------------

class _OCRBackend:
    """Abstract OCR wrapper."""
    def read(self, image: np.ndarray) -> List[Tuple[str, float]]:
        raise NotImplementedError


class _EasyOCRBackend(_OCRBackend):
    def __init__(self):
        self._reader = None

    def _load(self):
        if self._reader is None:
            import easyocr  # type: ignore
            self._reader = easyocr.Reader(["en"], gpu=False)

    def read(self, image: np.ndarray) -> List[Tuple[str, float]]:
        try:
            self._load()
            results = self._reader.readtext(image)
            return [(text, float(conf)) for (_, text, conf) in results]
        except Exception as exc:
            LOGGER.warning("EasyOCR failed: %s", exc)
            return []


class _PaddleOCRBackend(_OCRBackend):
    def __init__(self):
        self._engine = None

    def _load(self):
        if self._engine is None:
            from paddleocr import PaddleOCR  # type: ignore
            self._engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

    def read(self, image: np.ndarray) -> List[Tuple[str, float]]:
        try:
            self._load()
            res = self._engine.ocr(image, cls=True)
            if not res or not res[0]:
                return []
            return [(line[1][0], float(line[1][1])) for line in res[0]]
        except Exception as exc:
            LOGGER.warning("PaddleOCR failed: %s", exc)
            return []


class _FallbackOCR(_OCRBackend):
    """No-op fallback when no OCR engine is installed."""
    def read(self, image: np.ndarray) -> List[Tuple[str, float]]:
        return []


def _get_ocr_backend() -> _OCRBackend:
    """Try EasyOCR → PaddleOCR → fallback."""
    try:
        import easyocr  # noqa: F401
        return _EasyOCRBackend()
    except ImportError:
        pass
    try:
        from paddleocr import PaddleOCR  # noqa: F401
        return _PaddleOCRBackend()
    except ImportError:
        pass
    LOGGER.info("No OCR engine available; LPR will return empty results.")
    return _FallbackOCR()


# ---- Plate region proposal --------------------------------------------------

def _propose_plate_region(
    vehicle_crop: np.ndarray,
) -> Optional[np.ndarray]:
    """Heuristic: license plates are usually in the bottom-third of a vehicle bbox.

    Returns a sub-crop likely to contain the plate, or None.
    """
    h, w = vehicle_crop.shape[:2]
    if h < 20 or w < 30:
        return None
    # Bottom 40% of the crop, middle 80% horizontally
    y_start = int(h * 0.6)
    x_start = int(w * 0.1)
    x_end = int(w * 0.9)
    return vehicle_crop[y_start:h, x_start:x_end]


# ---- Color classification --------------------------------------------------

def classify_color(vehicle_crop: np.ndarray) -> str:
    """Return dominant colour name from a vehicle crop (requires cv2)."""
    try:
        import cv2  # type: ignore
    except ImportError:
        return "unknown"

    hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)
    best_color = "unknown"
    best_count = 0

    for color_name, (lower, upper) in _COLOR_RANGES.items():
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        count = int(cv2.countNonZero(mask))
        if count > best_count:
            best_count = count
            best_color = color_name

    return best_color


# ---- Vehicle Intelligence Engine --------------------------------------------

class VehicleEngine:
    """Processes vehicle detections: type classification, color, LPR."""

    def __init__(self, ocr_backend: Optional[_OCRBackend] = None, plate_region: str = "GENERIC"):
        self._ocr = ocr_backend or _get_ocr_backend()
        self._plate_pattern = _PLATE_PATTERNS.get(plate_region, _PLATE_PATTERNS["GENERIC"])

    def process_detections(
        self,
        detections: List[Dict],
        frame: Optional[np.ndarray] = None,
        timestamp: Optional[datetime] = None,
    ) -> List[VehicleInfo]:
        """Extract vehicle info from a list of detections.

        If ``frame`` is provided, attempts colour classification and LPR.
        """
        ts = timestamp or datetime.utcnow()
        results: List[VehicleInfo] = []

        for det in detections:
            class_name = det.get("class_name", "")
            if class_name not in VEHICLE_CLASSES:
                continue

            bbox = det.get("bbox", [0, 0, 0, 0])
            track_id = det.get("track_id", "unknown")

            info = VehicleInfo(
                track_id=track_id,
                vehicle_type=class_name,
                confidence=det.get("confidence", 0.0),
                timestamp=ts,
            )

            if frame is not None:
                crop = self._crop(frame, bbox)
                if crop is not None and crop.size > 0:
                    info.color = classify_color(crop)
                    info.plate = self._read_plate(crop)

            results.append(info)

        return results

    def _crop(self, frame: np.ndarray, bbox: list) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(w, int(bbox[2]))
        y2 = min(h, int(bbox[3]))
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _read_plate(self, vehicle_crop: np.ndarray) -> Optional[PlateResult]:
        plate_region = _propose_plate_region(vehicle_crop)
        if plate_region is None:
            return None
        raw_results = self._ocr.read(plate_region)
        if not raw_results:
            return None
        # Pick highest-confidence result that matches a plate pattern
        for text, conf in sorted(raw_results, key=lambda x: -x[1]):
            cleaned = text.upper().strip()
            if self._plate_pattern.match(cleaned):
                return PlateResult(text=cleaned, confidence=conf)
        # If nothing matches pattern, return best result if confidence high enough
        text, conf = raw_results[0]
        if conf >= 0.5:
            return PlateResult(text=text.upper().strip(), confidence=conf)
        return None


__all__ = [
    "PlateResult",
    "VehicleInfo",
    "VehicleEngine",
    "classify_color",
    "VEHICLE_CLASSES",
]
