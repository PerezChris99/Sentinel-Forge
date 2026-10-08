"""Tests for the behavior analysis engine."""
from datetime import datetime, timedelta

from analytics.behavior import (
    BehaviorEngine,
    BehaviorType,
    LoiteringDetector,
    CrowdDensityEstimator,
    SpeedDirectionAnalyzer,
    ZoneIntrusionDetector,
    TailgatingDetector,
    Zone,
)


def _make_zone(**kwargs):
    defaults = {
        "zone_id": "z1",
        "name": "Test Zone",
        "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)],
        "zone_type": "general",
        "max_dwell_seconds": 10.0,
        "max_crowd": 2,
    }
    defaults.update(kwargs)
    return Zone(**defaults)


def _track(tid="t1", bbox=None, speed=0.0, velocity=None, class_name="person", dwell=0.0):
    return {
        "track_id": tid,
        "bbox": bbox or [25, 25, 75, 75],
        "class_name": class_name,
        "speed": speed,
        "velocity": velocity or [0.0, 0.0],
        "dwell_seconds": dwell,
        "camera_id": "cam1",
    }


class TestLoiteringDetector:
    def test_no_loitering_initially(self):
        zone = _make_zone()
        det = LoiteringDetector([zone])
        evts = det.update([_track()], datetime(2026, 1, 1))
        assert len(evts) == 0

    def test_loitering_fires_after_threshold(self):
        zone = _make_zone(max_dwell_seconds=5.0)
        det = LoiteringDetector([zone])
        ts1 = datetime(2026, 1, 1)
        det.update([_track()], ts1)
        evts = det.update([_track()], ts1 + timedelta(seconds=10))
        assert len(evts) == 1
        assert evts[0].behavior_type == BehaviorType.LOITERING

    def test_not_in_zone(self):
        zone = _make_zone()
        det = LoiteringDetector([zone])
        # Track outside zone
        evts = det.update([_track(bbox=[200, 200, 250, 250])], datetime(2026, 1, 1))
        assert len(evts) == 0


class TestCrowdDensity:
    def test_no_event_below_threshold(self):
        zone = _make_zone(max_crowd=5)
        est = CrowdDensityEstimator([zone])
        evts = est.update([_track(tid="t1"), _track(tid="t2")])
        assert len(evts) == 0

    def test_event_above_threshold(self):
        zone = _make_zone(max_crowd=2)
        est = CrowdDensityEstimator([zone])
        tracks = [_track(tid=f"t{i}") for i in range(4)]
        evts = est.update(tracks)
        assert len(evts) == 1
        assert evts[0].behavior_type == BehaviorType.CROWD_DENSITY


class TestSpeedDirection:
    def test_speed_anomaly(self):
        ana = SpeedDirectionAnalyzer(speed_threshold=10.0)
        evts = ana.update([_track(speed=50.0)])
        assert len(evts) == 1
        assert evts[0].behavior_type == BehaviorType.SPEED_ANOMALY

    def test_no_anomaly(self):
        ana = SpeedDirectionAnalyzer(speed_threshold=100.0)
        evts = ana.update([_track(speed=5.0)])
        assert len(evts) == 0

    def test_wrong_way(self):
        ana = SpeedDirectionAnalyzer(
            speed_threshold=100.0,
            expected_direction=(1.0, 0.0),
            direction_tolerance_deg=45.0,
        )
        evts = ana.update([_track(speed=20.0, velocity=[-10.0, 0.0])])
        assert any(e.behavior_type == BehaviorType.WRONG_WAY for e in evts)

    def test_stopped_vehicle(self):
        ana = SpeedDirectionAnalyzer()
        evts = ana.detect_stopped_vehicles(
            [_track(class_name="car", speed=0.5, dwell=120.0)],
            min_dwell=60.0,
        )
        assert len(evts) == 1
        assert evts[0].behavior_type == BehaviorType.STOPPED_VEHICLE


class TestZoneIntrusion:
    def test_intrusion_event(self):
        zone = _make_zone(zone_type="restricted")
        det = ZoneIntrusionDetector([zone])
        evts = det.update([_track()])
        assert len(evts) == 1
        assert evts[0].behavior_type == BehaviorType.ZONE_INTRUSION

    def test_no_repeat_event(self):
        zone = _make_zone(zone_type="restricted")
        det = ZoneIntrusionDetector([zone])
        det.update([_track()])
        evts = det.update([_track()])  # same track still inside
        assert len(evts) == 0

    def test_general_zone_ignored(self):
        zone = _make_zone(zone_type="general")
        det = ZoneIntrusionDetector([zone])
        evts = det.update([_track()])
        assert len(evts) == 0


class TestTailgating:
    def test_tailgating_detected(self):
        zone = _make_zone(zone_type="access_point")
        det = TailgatingDetector([zone], time_gap=5.0)
        ts = datetime(2026, 1, 1)
        det.update([_track(tid="t1")], ts)
        evts = det.update([_track(tid="t2")], ts + timedelta(seconds=2))
        assert len(evts) == 1
        assert evts[0].behavior_type == BehaviorType.TAILGATING

    def test_no_tailgating_if_gap_too_large(self):
        zone = _make_zone(zone_type="access_point")
        det = TailgatingDetector([zone], time_gap=3.0)
        ts = datetime(2026, 1, 1)
        det.update([_track(tid="t1")], ts)
        evts = det.update([_track(tid="t2")], ts + timedelta(seconds=10))
        assert len(evts) == 0


class TestBehaviorEngine:
    def test_process_returns_combined_events(self):
        zone = _make_zone(zone_type="restricted")
        engine = BehaviorEngine([zone])
        engine.speed = SpeedDirectionAnalyzer(speed_threshold=5.0)
        evts = engine.process([_track(speed=20.0)])
        # Should get at least speed anomaly + zone intrusion
        types = {e.behavior_type for e in evts}
        assert BehaviorType.SPEED_ANOMALY in types
        assert BehaviorType.ZONE_INTRUSION in types

    def test_event_log_accumulates(self):
        engine = BehaviorEngine([])
        engine.speed = SpeedDirectionAnalyzer(speed_threshold=5.0)
        engine.process([_track(speed=20.0)])
        engine.process([_track(speed=30.0)])
        assert len(engine.all_events) >= 2
        engine.clear_log()
        assert len(engine.all_events) == 0
