"""
Unit tests for detection/tracker.py — IoU-based Tracker.
These tests are pure-Python and don't require opencv or ultralytics.
"""
import pytest
from datetime import datetime

from detection.tracker import Tracker, _iou


class TestIoU:
    def test_full_overlap(self):
        box = (0, 0, 10, 10)
        assert _iou(box, box) == pytest.approx(1.0)

    def test_no_overlap(self):
        a = (0, 0, 5, 5)
        b = (10, 10, 15, 15)
        assert _iou(a, b) == pytest.approx(0.0)

    def test_partial_overlap(self):
        a = (0, 0, 10, 10)
        b = (5, 5, 15, 15)
        # Intersection: (5,5)-(10,10) = 6x6 = 36
        # Union: 2*121 - 36 = 206  (each box = 11*11 = 121)
        # IoU = 36 / 206 ≈ 0.175
        iou = _iou(a, b)
        assert 0.1 < iou < 0.3  # reasonable overlap


class TestTracker:
    def test_creates_tracks_on_first_frame(self):
        tracker = Tracker()
        dets = [
            {"bbox": [0, 0, 10, 10], "class_name": "person"},
            {"bbox": [50, 50, 60, 60], "class_name": "car"},
        ]
        tracks = tracker.update(dets)
        assert len(tracks) == 2
        assert all("track_id" in t for t in tracks)

    def test_persistent_track_id_across_frames(self):
        tracker = Tracker()
        det1 = [{"bbox": [0, 0, 10, 10], "class_name": "person"}]
        tracks1 = tracker.update(det1)
        tid = tracks1[0]["track_id"]

        # Small movement — should match
        det2 = [{"bbox": [1, 1, 11, 11], "class_name": "person"}]
        tracks2 = tracker.update(det2)
        assert len(tracks2) == 1
        assert tracks2[0]["track_id"] == tid

    def test_prunes_lost_tracks(self):
        tracker = Tracker(max_lost_frames=2)
        det = [{"bbox": [0, 0, 10, 10], "class_name": "person"}]
        tracker.update(det)

        # No detections for 3 frames
        for _ in range(3):
            tracks = tracker.update([])
        assert len(tracks) == 0  # pruned

    def test_assigns_new_id_for_distant_detection(self):
        tracker = Tracker()
        det1 = [{"bbox": [0, 0, 10, 10], "class_name": "person"}]
        tracks1 = tracker.update(det1)
        old_id = tracks1[0]["track_id"]

        # Far away detection — should create new track
        det2 = [{"bbox": [500, 500, 510, 510], "class_name": "person"}]
        tracks2 = tracker.update(det2)
        # Old track is lost count +1, new track created
        assert len(tracks2) == 2 or any(t["track_id"] != old_id for t in tracks2)
