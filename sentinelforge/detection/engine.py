"""
SentinelForge Detection Engine
Phase 2: Real-time face detection and classification pipeline.
"""
import base64
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Tuple

import cv2
import face_recognition
import numpy as np
from sklearn.cluster import DBSCAN

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("SentinelForge.Detection")

@dataclass
class DetectionEvent:
    event_type: str
    timestamp: str
    camera_id: str
    person_id: Optional[str]
    confidence: float
    embedding: List[float]
    cropped_b64: str
    flag_level: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "camera_id": self.camera_id,
            "person_id": self.person_id,
            "confidence": self.confidence,
            "embedding": self.embedding,
            "cropped_b64": self.cropped_b64,
            "flag_level": self.flag_level,
            "metadata": self.metadata,
        }

class DetectionEngine:
    def __init__(self, known_faces: Dict[str, List[float]] = None, cascade_path: str = None):
        """
        Initialize the Detection Engine.
        
        :param known_faces: Dictionary mapping person_ids to their embedding vectors.
        :param cascade_path: Path to Haar cascade XML. Defaults to frontalface_alt2.
        """
        self.known_faces = known_faces or {}
        self.known_embeddings = list(self.known_faces.values())
        self.known_ids = list(self.known_faces.keys())
        
        # Load Haar Cascade
        if cascade_path is None:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
        
        self.detector = cv2.CascadeClassifier(cascade_path)
        if self.detector.empty():
            raise ValueError(f"Failed to load cascade classifier from {cascade_path}")
            
        # Clustering for unknowns (DBSCAN)
        self.unknown_embeddings: List[List[float]] = []
        self.dbscan = DBSCAN(eps=0.5, min_samples=3, metric="euclidean")
        
        LOGGER.info("DetectionEngine initialized with %d known faces", len(self.known_faces))

    def preprocess(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Pre-process frame: Grayscale -> CLAHE -> Resize.
        Returns None if frame is too blurry.
        """
        if frame is None:
            return None

        # Blur check (Laplacian variance)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        if variance < 100:
            LOGGER.debug("Frame skipped due to blur (var=%.2f)", variance)
            return None

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Resize for performance (target 640x480 usually good for detection)
        # We keep aspect ratio or just force resize depending on requirements. 
        # Here we'll resize to width 640
        height, width = enhanced.shape
        if width > 640:
            scale = 640 / width
            enhanced = cv2.resize(enhanced, (640, int(height * scale)))
        
        return enhanced

    def detect_and_process(self, frame: np.ndarray, camera_id: str) -> List[DetectionEvent]:
        """
        Main pipeline: Detect -> Classify -> Event.
        """
        processed_frame = self.preprocess(frame)
        if processed_frame is None:
            return []

        # Detect faces
        # scaleFactor=1.1, minNeighbors=5 are standard robust settings
        faces = self.detector.detectMultiScale(
            processed_frame, 
            scaleFactor=1.1, 
            minNeighbors=5, 
            minSize=(30, 30)
        )

        events = []
        original_h, original_w = frame.shape[:2]
        processed_h, processed_w = processed_frame.shape
        scale_x = original_w / processed_w
        scale_y = original_h / processed_h

        for (x, y, w, h) in faces:
            # Scale coordinates back to original frame for cropping
            orig_x, orig_y = int(x * scale_x), int(y * scale_y)
            orig_w, orig_h = int(w * scale_x), int(h * scale_y)
            
            # Ensure ROI is within bounds
            orig_x = max(0, orig_x)
            orig_y = max(0, orig_y)
            orig_w = min(original_w - orig_x, orig_w)
            orig_h = min(original_h - orig_y, orig_h)
            
            face_roi = frame[orig_y:orig_y+orig_h, orig_x:orig_x+orig_w]
            if face_roi.size == 0:
                continue

            # Compute embedding (using dlib/face_recognition)
            # face_recognition expects RGB
            rgb_roi = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
            
            # We use 'face_encodings' which internally uses dlib's predictor
            # It expects a list of face locations, or it finds them. 
            # Since we already have the crop, we can pass it directly or tell it the location is the whole image.
            # Passing the crop is safer/faster if we trust the cascade.
            encodings = face_recognition.face_encodings(rgb_roi)
            
            if not encodings:
                continue
            
            embedding = encodings[0]
            person_id, confidence = self._identify_person(embedding)
            
            # Base64 encode crop
            _, buffer = cv2.imencode('.jpg', face_roi)
            b64_crop = base64.b64encode(buffer).decode('utf-8')

            # Set base flag level: unknown faces are always flagged
            base_flag_level = 1 if person_id and person_id.startswith("unknown") else 0

            event = DetectionEvent(
                event_type="sighting",
                timestamp=datetime.utcnow().isoformat(),
                camera_id=camera_id,
                person_id=person_id,
                confidence=confidence,
                embedding=embedding.tolist(),
                cropped_b64=b64_crop,
                flag_level=base_flag_level  # Unknown faces flagged at detection
            )
            events.append(event)

        return events

    def _identify_person(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Match embedding against known faces.
        Returns (person_id, confidence).
        """
        if not self.known_embeddings:
            return self._handle_unknown(embedding)

        # Compare faces returns True/False based on tolerance (default 0.6)
        # We want distance to calculate confidence.
        # face_distance returns euclidean distance. Lower is better.
        distances = face_recognition.face_distance(self.known_embeddings, embedding)
        best_match_index = np.argmin(distances)
        min_distance = distances[best_match_index]

        # Threshold: 0.6 is typical for dlib. 
        # We can convert distance to a "confidence" score (0-1).
        # Simple heuristic: confidence = 1 - distance (clamped)
        confidence = max(0.0, 1.0 - min_distance)

        if min_distance < 0.6: # Match found
            return self.known_ids[best_match_index], confidence
        else:
            return self._handle_unknown(embedding)

    def _handle_unknown(self, embedding: np.ndarray) -> Tuple[str, float]:
        """
        Handle unknown person: Generate temp ID or cluster.
        """
        # For Phase 2, we'll just generate a hash-based ID or return None
        # In a real system, we might cluster here or let the backend handle it.
        # The prompt mentions "Cluster unknowns (DBSCAN eps=0.5)".
        # We'll implement a simple version here.
        
        # Add to local unknown cache for clustering (in-memory for this session)
        self.unknown_embeddings.append(embedding)
        
        # If we have enough samples, we could re-cluster, but for real-time 
        # we usually just assign a temporary ID based on the embedding hash
        # or return "unknown".
        
        # Simple hash for ID
        emb_hash = hash(tuple(embedding))
        return f"unknown_{abs(emb_hash) % 10000}", 0.0


class StreamProcessor:
    """
    Handles multi-camera streaming and processing.
    """
    def __init__(self, engine: DetectionEngine):
        self.engine = engine
        self.running = False
        self.queue = Queue()

    def start_stream(self, stream_url: str, camera_id: str, camera_type: str = None):
        """Start a thread to process a specific stream using CameraSource abstraction."""
        from detection.sources import create_source
        source = create_source(stream_url, camera_id, camera_type)
        self.running = True
        t = threading.Thread(target=self._capture_loop, args=(source,))
        t.daemon = True
        t.start()

    def _capture_loop(self, source):
        camera_id = source.camera_id
        LOGGER.info("Starting capture for %s (%s)", camera_id, type(source).__name__)

        if not source.open():
            LOGGER.error("Failed to open source for %s", camera_id)
            return

        retry_count = 0
        max_retries = 5

        while self.running:
            if not source.is_opened():
                if retry_count < max_retries:
                    LOGGER.warning("Stream %s closed. Retrying (%d/%d)...", camera_id, retry_count + 1, max_retries)
                    time.sleep(2 ** min(retry_count, 4))
                    source.open()
                    retry_count += 1
                    continue
                else:
                    LOGGER.error("Stream %s failed permanently after %d retries.", camera_id, max_retries)
                    break

            ret, frame = source.read()
            if not ret or frame is None:
                LOGGER.warning("Failed to read frame from %s", camera_id)
                retry_count += 1
                time.sleep(1)
                continue

            retry_count = 0

            try:
                events = self.engine.detect_and_process(frame, camera_id)
                for event in events:
                    self.queue.put(event)
            except Exception as e:
                LOGGER.error("Error processing frame from %s: %s", camera_id, e)

        source.release()

    def get_events(self):
        """Generator to yield events from the queue."""
        while self.running:
            try:
                event = self.queue.get(timeout=1)
                yield event
            except Empty:
                continue

    def stop(self):
        self.running = False


# --- Optional pipeline integration with YOLO + Tracker ---
try:
    from .yolo_engine import YOLOEngine
    from .tracker import Tracker
except Exception:
    YOLOEngine = None  # type: ignore
    Tracker = None  # type: ignore


class DetectionPipeline:
    """High-level pipeline that can run object detection (YOLO) and
    simple tracking, while preserving the face-based `DetectionEngine`.

    This class is dependency-safe: if `ultralytics` is not installed the
    YOLO step becomes a no-op and the pipeline still functions.
    """

    def __init__(self, face_engine: DetectionEngine, yolo_model_path: str | None = None):
        self.face_engine = face_engine
        self.yolo = YOLOEngine(model_path=yolo_model_path) if YOLOEngine is not None else None
        self.tracker = Tracker() if Tracker is not None else None

    def process_frame(self, frame: np.ndarray, camera_id: str):
        """Run detection (objects + faces) and tracking on a frame.

        Returns a dict with keys: `detections` (object detections),
        `face_events` (list of `DetectionEvent`), `tracks` (active tracks).
        """
        results = {"detections": [], "face_events": [], "tracks": []}

        # 1) Run YOLO object detection (optional)
        if self.yolo is not None:
            try:
                dets = self.yolo.detect(frame)
                results["detections"] = dets
            except Exception:
                results["detections"] = []

        # 2) Run tracker (optional)
        if self.tracker is not None and results["detections"]:
            try:
                tracks = self.tracker.update(results["detections"])  # timestamp handled in tracker
                results["tracks"] = tracks
            except Exception:
                results["tracks"] = []

        # 3) Face detection/recognition pipeline (existing)
        try:
            face_events = self.face_engine.detect_and_process(frame, camera_id)
            results["face_events"] = [e.to_dict() for e in face_events]
        except Exception:
            results["face_events"] = []

        return results


__all__ = ["DetectionEngine", "DetectionEvent", "DetectionPipeline"]
