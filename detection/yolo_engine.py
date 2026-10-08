"""
YOLO-based detection engine with optional dependency fallbacks.

This module attempts to use `ultralytics.YOLO` when available. When the
dependency is not installed, it exposes a lightweight fallback that
returns no detections so the rest of the system can be exercised without
installing heavy CV packages.

The API is intentionally small: `YOLOEngine.detect(frame)` returns a list
of detection dicts: {"class_id", "class_name", "confidence", "bbox"}
where bbox = [x1, y1, x2, y2].
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)


class _FallbackYOLO:
    """Fallback when ultralytics/YOLov8 isn't available.

    It provides the same interface but returns an empty list of detections.
    """

    def __init__(self, *args, **kwargs):
        LOGGER.warning("YOLO model not available; using fallback detector")

    def predict(self, frame: np.ndarray, imgsz: int = 640):
        # Return an object-compatible with the minimal attributes used below
        class Result:
            boxes = []

        return [Result()]


try:
    # ultralytics provides a convenient YOLO wrapper
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO = _FallbackYOLO  # type: ignore


class YOLOEngine:
    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        """Initialize YOLO engine.

        If `ultralytics` is not installed, this will use a no-op fallback.
        """
        self.device = device
        if model_path is None:
            # default to a lightweight COCO model name; actual resolution
            # and weights are environment dependent.
            model_path = "yolov8n.pt"

        try:
            self.model = YOLO(model_path)
            LOGGER.info("Loaded YOLO model: %s", model_path)
        except Exception as e:
            LOGGER.warning("Failed to load YOLO model (%s): %s", model_path, e)
            # Do not call the failing provider constructor again. The internal
            # fallback is dependency-free and is guaranteed to return safely.
            self.model = _FallbackYOLO()

        # minimal label map for COCO-like models; can be extended by user
        self.label_map = {
            0: "person",
            1: "bicycle",
            2: "car",
            3: "motorbike",
            4: "aeroplane",
            5: "bus",
            6: "train",
            7: "truck",
            8: "boat",
            9: "traffic_light",
        }

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.3) -> List[Dict]:
        """Run detection on a single frame.

        Returns a list of dicts: {class_id, class_name, confidence, bbox}
        bbox uses pixel coordinates [x1, y1, x2, y2].
        """
        if frame is None:
            return []

        try:
            results = self.model.predict(frame, imgsz=640)
        except Exception as e:
            LOGGER.debug("YOLO predict failed; returning no detections: %s", e)
            return []

        detections: List[Dict] = []
        for res in results:
            # ultralytics result.boxes contains tensor-like boxes; but the
            # fallback exposes an empty list. We do robust attribute checks.
            boxes = getattr(res, "boxes", []) or []
            for b in boxes:
                try:
                    # ultralytics provides xyxy, conf, cls
                    xyxy = b.xyxy[0].tolist() if hasattr(b, "xyxy") else list(b[:4])
                    conf = float(b.conf[0]) if hasattr(b, "conf") else float(b[4])
                    cls = int(b.cls[0]) if hasattr(b, "cls") else int(b[5])
                except Exception:
                    # Skip malformed box
                    continue

                if conf < conf_threshold:
                    continue

                class_name = self.label_map.get(cls, f"class_{cls}")
                detections.append(
                    {
                        "class_id": cls,
                        "class_name": class_name,
                        "confidence": conf,
                        "bbox": [int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])],
                    }
                )

        return detections


__all__ = ["YOLOEngine"]
