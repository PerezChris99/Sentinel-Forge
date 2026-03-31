"""Tests for the geospatial zone engine."""
from datetime import datetime, timedelta

from analytics.geospatial import (
    GeospatialEngine,
    GeoZone,
    CameraPlacement,
    HeatmapCell,
)


def _zone(**kwargs):
    defaults = {
        "zone_id": "z1",
        "name": "Main Lobby",
        "polygon": [(0, 0), (100, 0), (100, 100), (0, 100)],
    }
    defaults.update(kwargs)
    return GeoZone(**defaults)


def _track(tid="t1", bbox=None):
    return {
        "track_id": tid,
        "bbox": bbox or [25, 25, 75, 75],
    }


class TestGeoZone:
    def test_contains_inside(self):
        z = _zone()
        assert z.contains(50, 50) is True

    def test_contains_outside(self):
        z = _zone()
        assert z.contains(200, 200) is False

    def test_centroid(self):
        z = _zone()
        cx, cy = z.centroid
        assert cx == 50.0
        assert cy == 50.0

    def test_area(self):
        z = _zone()
        assert z.area == 10000.0

    def test_to_dict(self):
        d = _zone().to_dict()
        assert d["zone_id"] == "z1"
        assert "polygon" in d


class TestGeospatialEngine:
    def test_add_remove_zone(self):
        engine = GeospatialEngine()
        engine.add_zone(_zone())
        assert len(engine.zones) == 1
        engine.remove_zone("z1")
        assert len(engine.zones) == 0

    def test_zones_for_point(self):
        engine = GeospatialEngine()
        engine.add_zone(_zone())
        assert len(engine.zones_for_point(50, 50)) == 1
        assert len(engine.zones_for_point(200, 200)) == 0

    def test_zone_occupancy(self):
        engine = GeospatialEngine()
        engine.add_zone(_zone())
        tracks = [_track(tid="t1"), _track(tid="t2", bbox=[200, 200, 250, 250])]
        occ = engine.zone_occupancy(tracks)
        assert occ["z1"] == 1

    def test_list_zones_filter(self):
        engine = GeospatialEngine()
        engine.add_zone(_zone(zone_id="a", zone_type="restricted"))
        engine.add_zone(_zone(zone_id="b", zone_type="general"))
        assert len(engine.list_zones(zone_type="restricted")) == 1


class TestCameraPlacement:
    def test_add_camera(self):
        engine = GeospatialEngine()
        cam = CameraPlacement(camera_id="cam1", x=50, y=50)
        engine.add_camera(cam)
        assert "cam1" in engine.cameras

    def test_nearest_camera(self):
        engine = GeospatialEngine()
        engine.add_camera(CameraPlacement(camera_id="cam1", x=0, y=0))
        engine.add_camera(CameraPlacement(camera_id="cam2", x=100, y=100))
        nearest = engine.nearest_camera(90, 90)
        assert nearest.camera_id == "cam2"

    def test_cameras_for_zone(self):
        engine = GeospatialEngine()
        engine.add_camera(CameraPlacement(camera_id="cam1", x=50, y=50))
        engine.add_zone(_zone(camera_ids=["cam1"]))
        cams = engine.cameras_for_zone("z1")
        assert len(cams) == 1


class TestHeatmap:
    def test_accumulate_and_get(self):
        engine = GeospatialEngine()
        engine.accumulate_heatmap([_track()])
        engine.accumulate_heatmap([_track()])
        cells = engine.get_heatmap(min_count=2)
        assert len(cells) >= 1
        assert cells[0].count >= 2

    def test_reset_heatmap(self):
        engine = GeospatialEngine()
        engine.accumulate_heatmap([_track()])
        engine.reset_heatmap()
        assert engine.get_heatmap() == []


class TestPaths:
    def test_record_and_get(self):
        engine = GeospatialEngine()
        ts = datetime(2026, 1, 1)
        engine.record_paths([_track()], ts)
        engine.record_paths([_track(bbox=[30, 30, 80, 80])], ts + timedelta(seconds=1))
        path = engine.get_path("t1")
        assert len(path) == 2

    def test_clear_paths(self):
        engine = GeospatialEngine()
        engine.record_paths([_track()])
        engine.clear_paths()
        assert engine.get_path("t1") == []


class TestExportState:
    def test_export(self):
        engine = GeospatialEngine()
        engine.add_zone(_zone())
        engine.add_camera(CameraPlacement(camera_id="cam1", x=0, y=0))
        state = engine.export_state()
        assert len(state["zones"]) == 1
        assert len(state["cameras"]) == 1
