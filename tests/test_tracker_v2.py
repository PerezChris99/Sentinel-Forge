"""Tests for the upgraded multi-object tracker with ReID support."""
import numpy as np
from datetime import datetime, timedelta

from detection.tracker import Tracker, _iou, _cosine_sim


class TestIoU:
    def test_perfect_overlap(self):
        assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_no_overlap(self):
        assert _iou((0, 0, 5, 5), (10, 10, 20, 20)) == 0.0

    def test_partial_overlap(self):
        score = _iou((0, 0, 10, 10), (5, 5, 15, 15))
        assert 0.1 < score < 0.5


class TestCosineSim:
    def test_identical(self):
        a = np.array([1, 0, 0])
        assert abs(_cosine_sim(a, a) - 1.0) < 1e-6

    def test_orthogonal(self):
        assert abs(_cosine_sim(np.array([1, 0]), np.array([0, 1]))) < 1e-6

    def test_zero_vector(self):
        assert _cosine_sim(np.zeros(3), np.ones(3)) == 0.0


class TestTrackerBasic:
    def test_creates_tracks_on_first_frame(self):
        tracker = Tracker()
        dets = [
            {"bbox": [10, 10, 50, 50], "class_name": "person"},
            {"bbox": [100, 100, 200, 200], "class_name": "car"},
        ]
        tracks = tracker.update(dets)
        assert len(tracks) == 2
        assert tracks[0]["class_name"] == "person"

    def test_matches_nearby_detection(self):
        tracker = Tracker()
        ts1 = datetime(2026, 1, 1, 12, 0, 0)
        ts2 = ts1 + timedelta(seconds=1)

        tracker.update([{"bbox": [10, 10, 50, 50], "class_name": "person"}], ts1)
        tracks = tracker.update([{"bbox": [12, 12, 52, 52], "class_name": "person"}], ts2)

        assert len(tracks) == 1
        assert tracks[0]["speed"] > 0

    def test_prunes_lost_tracks(self):
        tracker = Tracker(max_lost_frames=2)
        ts = datetime(2026, 1, 1)

        tracker.update([{"bbox": [10, 10, 50, 50]}], ts)
        for i in range(4):
            tracker.update([], ts + timedelta(seconds=i + 1))

        assert len(tracker.tracks) == 0

    def test_dwell_time_calculated(self):
        tracker = Tracker()
        ts1 = datetime(2026, 1, 1, 12, 0, 0)
        ts2 = ts1 + timedelta(seconds=10)

        tracker.update([{"bbox": [10, 10, 50, 50]}], ts1)
        tracks = tracker.update([{"bbox": [11, 11, 51, 51]}], ts2)

        assert tracks[0]["dwell_seconds"] == 10.0


class TestTrackerReID:
    def test_reid_matching(self):
        tracker = Tracker(use_reid=True)
        emb = list(np.random.randn(128))
        ts1 = datetime(2026, 1, 1, 12, 0, 0)
        ts2 = ts1 + timedelta(seconds=1)

        tracker.update([{"bbox": [10, 10, 50, 50], "embedding": emb}], ts1)
        tracks = tracker.update([{"bbox": [12, 12, 52, 52], "embedding": emb}], ts2)

        assert len(tracks) == 1
        assert tracks[0]["has_embedding"] is True

    def test_cross_camera_reconcile(self):
        t1 = Tracker()
        t2 = Tracker()
        emb = list(np.random.randn(128))
        ts = datetime(2026, 1, 1)

        t1.update([{"bbox": [10, 10, 50, 50], "embedding": emb}], ts, camera_id="cam1")
        t2.update([{"bbox": [10, 10, 50, 50], "embedding": emb}], ts, camera_id="cam2")

        matches = t1.reconcile_cross_camera(t2, similarity_threshold=0.9)
        assert len(matches) == 1
        assert matches[0][2] > 0.9

    def test_camera_tracking(self):
        tracker = Tracker()
        ts = datetime(2026, 1, 1)

        tracker.update([{"bbox": [10, 10, 50, 50]}], ts, camera_id="cam1")
        tracks = tracker.update([{"bbox": [11, 11, 51, 51]}], ts + timedelta(seconds=1), camera_id="cam2")

        assert "cam1" in tracks[0]["cameras_seen"]
        assert "cam2" in tracks[0]["cameras_seen"]
