"""
Geospatial Zone Engine for SentinelForge.

Provides:
- Zone management (CRUD for polygon zones)
- Point-in-polygon queries (which zone is a detection in?)
- Camera-to-zone assignment
- Heatmap data generation from track paths
- Path / trajectory visualization data

No external GIS dependencies — pure Python + numpy.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)


# ---- Zone definition --------------------------------------------------------

@dataclass
class GeoZone:
    """Represents a named polygon zone on a camera view / site map."""
    zone_id: str
    name: str
    polygon: List[Tuple[float, float]]  # [(x,y), ...]
    zone_type: str = "general"  # general | restricted | access_point | parking | corridor
    floor: int = 0
    camera_ids: List[str] = field(default_factory=list)
    max_dwell_seconds: float = 300.0
    max_crowd: int = 20
    metadata: dict = field(default_factory=dict)

    def contains(self, x: float, y: float) -> bool:
        """Ray-casting point-in-polygon."""
        n = len(self.polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.polygon[i]
            xj, yj = self.polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
        return inside

    @property
    def centroid(self) -> Tuple[float, float]:
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    @property
    def area(self) -> float:
        """Shoelace formula for polygon area."""
        n = len(self.polygon)
        a = 0.0
        for i in range(n):
            j = (i + 1) % n
            a += self.polygon[i][0] * self.polygon[j][1]
            a -= self.polygon[j][0] * self.polygon[i][1]
        return abs(a) / 2.0

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Camera Placement -------------------------------------------------------

@dataclass
class CameraPlacement:
    """Maps a camera to a position on the site map."""
    camera_id: str
    x: float
    y: float
    floor: int = 0
    fov_angle: float = 90.0  # degrees
    fov_direction: float = 0.0  # degrees from north (CW)
    coverage_radius: float = 200.0  # pixels on map

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Heatmap bin -----------------------------------------------------------

@dataclass
class HeatmapCell:
    x: int
    y: int
    count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Geospatial Engine -----------------------------------------------------

class GeospatialEngine:
    """Manages zones, camera placements, and spatial queries."""

    def __init__(self):
        self.zones: Dict[str, GeoZone] = {}
        self.cameras: Dict[str, CameraPlacement] = {}
        # Heatmap accumulator: (grid_x, grid_y) -> count
        self._heatmap: Dict[Tuple[int, int], int] = defaultdict(int)
        self._heatmap_cell_size: int = 20  # pixels per cell
        # Track path history: track_id -> [(x, y, timestamp)]
        self._paths: Dict[str, List[Tuple[float, float, str]]] = defaultdict(list)

    # ---- Zone CRUD ----------------------------------------------------------

    def add_zone(self, zone: GeoZone) -> GeoZone:
        self.zones[zone.zone_id] = zone
        LOGGER.info("Added zone %s (%s)", zone.zone_id, zone.name)
        return zone

    def remove_zone(self, zone_id: str) -> bool:
        if zone_id in self.zones:
            del self.zones[zone_id]
            return True
        return False

    def get_zone(self, zone_id: str) -> Optional[GeoZone]:
        return self.zones.get(zone_id)

    def list_zones(self, zone_type: Optional[str] = None, floor: Optional[int] = None) -> List[GeoZone]:
        result = list(self.zones.values())
        if zone_type:
            result = [z for z in result if z.zone_type == zone_type]
        if floor is not None:
            result = [z for z in result if z.floor == floor]
        return result

    # ---- Camera placement ---------------------------------------------------

    def add_camera(self, cam: CameraPlacement) -> CameraPlacement:
        self.cameras[cam.camera_id] = cam
        return cam

    def remove_camera(self, camera_id: str) -> bool:
        if camera_id in self.cameras:
            del self.cameras[camera_id]
            return True
        return False

    def cameras_for_zone(self, zone_id: str) -> List[CameraPlacement]:
        zone = self.zones.get(zone_id)
        if not zone:
            return []
        return [self.cameras[cid] for cid in zone.camera_ids if cid in self.cameras]

    # ---- Spatial queries ----------------------------------------------------

    def zones_for_point(self, x: float, y: float) -> List[GeoZone]:
        """Return all zones that contain the given point."""
        return [z for z in self.zones.values() if z.contains(x, y)]

    def zone_occupancy(self, tracks: List[Dict]) -> Dict[str, int]:
        """Count number of tracks inside each zone."""
        counts: Dict[str, int] = {zid: 0 for zid in self.zones}
        for track in tracks:
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0
            for zid, zone in self.zones.items():
                if zone.contains(cx, cy):
                    counts[zid] += 1
        return counts

    # ---- Heatmap generation -------------------------------------------------

    def accumulate_heatmap(self, tracks: List[Dict]):
        """Add track center points to the heatmap accumulator."""
        cs = self._heatmap_cell_size
        for track in tracks:
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0
            gx = int(cx // cs)
            gy = int(cy // cs)
            self._heatmap[(gx, gy)] += 1

    def get_heatmap(self, min_count: int = 1) -> List[HeatmapCell]:
        """Return heatmap cells above the minimum count."""
        return [
            HeatmapCell(x=gx, y=gy, count=c)
            for (gx, gy), c in self._heatmap.items()
            if c >= min_count
        ]

    def reset_heatmap(self):
        self._heatmap.clear()

    # ---- Path / trajectory recording ----------------------------------------

    def record_paths(self, tracks: List[Dict], timestamp: Optional[datetime] = None):
        ts = (timestamp or datetime.utcnow()).isoformat()
        for track in tracks:
            tid = track["track_id"]
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0
            self._paths[tid].append((cx, cy, ts))

    def get_path(self, track_id: str) -> List[Tuple[float, float, str]]:
        return list(self._paths.get(track_id, []))

    def get_all_paths(self) -> Dict[str, List[Tuple[float, float, str]]]:
        return {tid: list(pts) for tid, pts in self._paths.items()}

    def clear_paths(self):
        self._paths.clear()

    # ---- Distance / coverage helpers ----------------------------------------

    @staticmethod
    def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def nearest_camera(self, x: float, y: float) -> Optional[CameraPlacement]:
        best: Optional[CameraPlacement] = None
        best_dist = float("inf")
        for cam in self.cameras.values():
            d = self.distance((x, y), (cam.x, cam.y))
            if d < best_dist:
                best_dist = d
                best = cam
        return best

    # ---- Serialization ------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "zones": [z.to_dict() for z in self.zones.values()],
            "cameras": [c.to_dict() for c in self.cameras.values()],
            "heatmap_cells": len(self._heatmap),
            "tracked_paths": len(self._paths),
        }


__all__ = [
    "GeoZone",
    "CameraPlacement",
    "HeatmapCell",
    "GeospatialEngine",
]
