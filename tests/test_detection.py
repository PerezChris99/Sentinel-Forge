import unittest
from unittest.mock import patch
import pytest
import numpy as np

pytest.importorskip("cv2")
pytest.importorskip("face_recognition")
from detection.engine import DetectionEngine, DetectionEvent

class TestDetectionEngine(unittest.TestCase):
    def setUp(self):
        # Mock the cascade classifier loading
        with patch('cv2.CascadeClassifier') as MockCascade:
            self.mock_detector = MockCascade.return_value
            self.mock_detector.empty.return_value = False
            self.engine = DetectionEngine(known_faces={"person1": [0.1]*128})

    def test_preprocess_blur(self):
        # Create a blurry image (solid color)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        processed = self.engine.preprocess(img)
        # Should be None because variance is 0 < 100
        self.assertIsNone(processed)

    def test_preprocess_valid(self):
        # Create a random noise image (high variance)
        img = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        processed = self.engine.preprocess(img)
        self.assertIsNotNone(processed)
        # Check resize width
        self.assertEqual(processed.shape[1], 640)

    @patch('face_recognition.face_encodings')
    def test_detect_and_process_known(self, mock_encodings):
        # Mock detection: one face at 10,10 size 50x50
        self.engine.detector.detectMultiScale.return_value = [(10, 10, 50, 50)]
        
        # Mock encoding: matches "person1"
        mock_encodings.return_value = [np.array([0.1]*128)]
        
        frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        events = self.engine.detect_and_process(frame, "cam1")
        
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].person_id, "person1")
        self.assertEqual(events[0].camera_id, "cam1")
        self.assertEqual(events[0].event_type, "sighting")

    @patch('face_recognition.face_encodings')
    def test_detect_and_process_unknown(self, mock_encodings):
        # Mock detection
        self.engine.detector.detectMultiScale.return_value = [(10, 10, 50, 50)]
        
        # Mock encoding: completely different from person1
        mock_encodings.return_value = [np.array([0.9]*128)]
        
        frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        events = self.engine.detect_and_process(frame, "cam1")
        
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].person_id.startswith("unknown"))
        # Unknown faces should be flagged at detection
        self.assertEqual(events[0].flag_level, 1)

if __name__ == '__main__':
    unittest.main()
