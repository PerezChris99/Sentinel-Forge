"""
Behavior Analysis Engine for SentinelForge.

Detects suspicious behavioral patterns from track data:
- Loitering (excessive dwell time in a zone)
- Crowd density anomalies
- Speed / direction anomalies
- Zone intrusion (enter restricted area)
- Tailgating (two people through access point in quick succession)

All detectors operate on track dicts produced by ``detection.tracker.Tracker``.
No heavy CV dependencies — pure Python + numpy.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)


# ---- Event types ------------------------------------------------------------

class BehaviorType(str, Enum):
    LOITERING = "loitering"
    CROWD_DENSITY = "crowd_density"
    SPEED_ANOMALY = "speed_anomaly"
    DIRECTION_ANOMALY = "direction_anomaly"
    ZONE_INTRUSION = "zone_intrusion"
    TAILGATING = "tailgating"
    STOPPED_VEHICLE = "stopped_vehicle"
    WRONG_WAY = "wrong_way"


@dataclass
class BehaviorEvent:
    behavior_type: BehaviorType
    severity: int  # 1-4
    track_id: str
    camera_id: Optional[str]
    zone_id: Optional[str]
    timestamp: datetime
    description: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["behavior_type"] = self.behavior_type.value
        d["timestamp"] = self.timestamp.isoformat()
        return d


# ---- Zone helper (used for intrusion / crowd calcs) ------------------------

@dataclass
class Zone:
    """Simple polygon zone for point-in-polygon checks."""
    zone_id: str
    name: str
    polygon: List[Tuple[float, float]]  # [(x,y), ...]
    zone_type: str = "general"  # general | restricted | access_point
    max_dwell_seconds: float = 300.0  # 5 min default loitering threshold
    max_crowd: int = 20

    def contains(self, x: float, y: float) -> bool:
        """Ray-casting point-in-polygon test."""
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


# ---- Loitering Detector ----------------------------------------------------

class LoiteringDetector:
    """Fires when a track stays inside a zone longer than its threshold."""

    def __init__(self, zones: Optional[List[Zone]] = None):
        self.zones = zones or []
        # track_id -> {zone_id: first_entered}
        self._presence: Dict[str, Dict[str, datetime]] = defaultdict(dict)

    def update(self, tracks: List[Dict], timestamp: Optional[datetime] = None) -> List[BehaviorEvent]:
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []
        active_ids = set()

        for track in tracks:
            tid = track["track_id"]
            active_ids.add(tid)
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0

            for zone in self.zones:
                if zone.contains(cx, cy):
                    if zone.zone_id not in self._presence[tid]:
                        self._presence[tid][zone.zone_id] = ts
                    else:
                        dwell = (ts - self._presence[tid][zone.zone_id]).total_seconds()
                        if dwell > zone.max_dwell_seconds:
                            severity = min(4, 1 + int(dwell / zone.max_dwell_seconds))
                            events.append(BehaviorEvent(
                                behavior_type=BehaviorType.LOITERING,
                                severity=severity,
                                track_id=tid,
                                camera_id=track.get("camera_id"),
                                zone_id=zone.zone_id,
                                timestamp=ts,
                                description=f"Track {tid} loitering in {zone.name} for {dwell:.0f}s",
                                metadata={"dwell_seconds": dwell},
                            ))
                else:
                    self._presence[tid].pop(zone.zone_id, None)

        # Clean up departed tracks
        for tid in list(self._presence.keys()):
            if tid not in active_ids:
                del self._presence[tid]

        return events


# ---- Crowd Density Estimator -----------------------------------------------

class CrowdDensityEstimator:
    """Counts tracks per zone per frame; fires when count exceeds threshold."""

    def __init__(self, zones: Optional[List[Zone]] = None):
        self.zones = zones or []

    def update(self, tracks: List[Dict], timestamp: Optional[datetime] = None) -> List[BehaviorEvent]:
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []

        zone_counts: Dict[str, int] = {z.zone_id: 0 for z in self.zones}
        for track in tracks:
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0
            for zone in self.zones:
                if zone.contains(cx, cy):
                    zone_counts[zone.zone_id] += 1

        for zone in self.zones:
            count = zone_counts[zone.zone_id]
            if count > zone.max_crowd:
                severity = min(4, 1 + (count - zone.max_crowd) // 5)
                events.append(BehaviorEvent(
                    behavior_type=BehaviorType.CROWD_DENSITY,
                    severity=severity,
                    track_id="zone_aggregate",
                    camera_id=None,
                    zone_id=zone.zone_id,
                    timestamp=ts,
                    description=f"Crowd density {count} in {zone.name} exceeds max {zone.max_crowd}",
                    metadata={"count": count, "max": zone.max_crowd},
                ))

        return events


# ---- Speed / Direction Analyzer ---------------------------------------------

class SpeedDirectionAnalyzer:
    """Detects abnormal speed or wrong-way movement for tracks."""

    def __init__(
        self,
        speed_threshold: float = 50.0,  # pixels/frame
        expected_direction: Optional[Tuple[float, float]] = None,
        direction_tolerance_deg: float = 90.0,
    ):
        self.speed_threshold = speed_threshold
        self.expected_direction = expected_direction  # (dx, dy) unit vector
        self.direction_tolerance_deg = direction_tolerance_deg

    def update(self, tracks: List[Dict], timestamp: Optional[datetime] = None) -> List[BehaviorEvent]:
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []

        for track in tracks:
            speed = track.get("speed", 0.0)
            velocity = track.get("velocity", [0.0, 0.0])

            # Speed anomaly
            if speed > self.speed_threshold:
                events.append(BehaviorEvent(
                    behavior_type=BehaviorType.SPEED_ANOMALY,
                    severity=min(4, 1 + int(speed / self.speed_threshold)),
                    track_id=track["track_id"],
                    camera_id=track.get("camera_id"),
                    zone_id=None,
                    timestamp=ts,
                    description=f"Track {track['track_id']} moving at {speed:.1f} px/frame",
                    metadata={"speed": speed, "threshold": self.speed_threshold},
                ))

            # Wrong-way detection
            if self.expected_direction and speed > 5.0:
                vx, vy = velocity[0], velocity[1]
                ex, ey = self.expected_direction
                dot = vx * ex + vy * ey
                mag_v = math.hypot(vx, vy)
                mag_e = math.hypot(ex, ey)
                if mag_v > 0 and mag_e > 0:
                    cos_angle = max(-1.0, min(1.0, dot / (mag_v * mag_e)))
                    angle_deg = math.degrees(math.acos(cos_angle))
                    if angle_deg > (180 - self.direction_tolerance_deg):
                        events.append(BehaviorEvent(
                            behavior_type=BehaviorType.WRONG_WAY,
                            severity=3,
                            track_id=track["track_id"],
                            camera_id=track.get("camera_id"),
                            zone_id=None,
                            timestamp=ts,
                            description=f"Track {track['track_id']} moving wrong way ({angle_deg:.0f}°)",
                            metadata={"angle_deg": angle_deg},
                        ))

        return events

    # Convenience: detect stopped vehicles
    def detect_stopped_vehicles(
        self,
        tracks: List[Dict],
        min_dwell: float = 60.0,
        timestamp: Optional[datetime] = None,
    ) -> List[BehaviorEvent]:
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []
        vehicle_classes = {"car", "truck", "bus", "motorcycle", "bicycle"}
        for track in tracks:
            if track.get("class_name") not in vehicle_classes:
                continue
            if track.get("speed", 0.0) < 2.0 and track.get("dwell_seconds", 0) > min_dwell:
                events.append(BehaviorEvent(
                    behavior_type=BehaviorType.STOPPED_VEHICLE,
                    severity=2,
                    track_id=track["track_id"],
                    camera_id=track.get("camera_id"),
                    zone_id=None,
                    timestamp=ts,
                    description=f"Vehicle {track['track_id']} stopped for {track.get('dwell_seconds',0):.0f}s",
                    metadata={"dwell_seconds": track.get("dwell_seconds", 0)},
                ))
        return events


# ---- Zone Intrusion Detector ------------------------------------------------

class ZoneIntrusionDetector:
    """Fires when a track enters a restricted zone."""

    def __init__(self, zones: Optional[List[Zone]] = None):
        self.zones = [z for z in (zones or []) if z.zone_type == "restricted"]
        self._inside: Dict[str, set] = defaultdict(set)  # track_id -> set of zone_ids

    def update(self, tracks: List[Dict], timestamp: Optional[datetime] = None) -> List[BehaviorEvent]:
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []
        active_ids = set()

        for track in tracks:
            tid = track["track_id"]
            active_ids.add(tid)
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0

            for zone in self.zones:
                currently_inside = zone.contains(cx, cy)
                was_inside = zone.zone_id in self._inside[tid]

                if currently_inside and not was_inside:
                    self._inside[tid].add(zone.zone_id)
                    events.append(BehaviorEvent(
                        behavior_type=BehaviorType.ZONE_INTRUSION,
                        severity=3,
                        track_id=tid,
                        camera_id=track.get("camera_id"),
                        zone_id=zone.zone_id,
                        timestamp=ts,
                        description=f"Track {tid} entered restricted zone {zone.name}",
                        metadata={"zone_name": zone.name},
                    ))
                elif not currently_inside and was_inside:
                    self._inside[tid].discard(zone.zone_id)

        for tid in list(self._inside.keys()):
            if tid not in active_ids:
                del self._inside[tid]

        return events


# ---- Tailgating Detector ----------------------------------------------------

class TailgatingDetector:
    """Detects two tracks passing through an access-point zone in quick succession."""

    def __init__(self, zones: Optional[List[Zone]] = None, time_gap: float = 3.0):
        self.zones = [z for z in (zones or []) if z.zone_type == "access_point"]
        self.time_gap = time_gap
        # zone_id -> last entry (track_id, timestamp)
        self._last_entry: Dict[str, Tuple[str, datetime]] = {}

    def update(self, tracks: List[Dict], timestamp: Optional[datetime] = None) -> List[BehaviorEvent]:
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []

        for track in tracks:
            tid = track["track_id"]
            cx = (track["bbox"][0] + track["bbox"][2]) / 2.0
            cy = (track["bbox"][1] + track["bbox"][3]) / 2.0

            for zone in self.zones:
                if zone.contains(cx, cy):
                    last = self._last_entry.get(zone.zone_id)
                    if last and last[0] != tid:
                        gap = (ts - last[1]).total_seconds()
                        if 0 < gap <= self.time_gap:
                            events.append(BehaviorEvent(
                                behavior_type=BehaviorType.TAILGATING,
                                severity=3,
                                track_id=tid,
                                camera_id=track.get("camera_id"),
                                zone_id=zone.zone_id,
                                timestamp=ts,
                                description=f"Tailgating: {tid} followed {last[0]} within {gap:.1f}s at {zone.name}",
                                metadata={"preceded_by": last[0], "gap_seconds": gap},
                            ))
                    self._last_entry[zone.zone_id] = (tid, ts)

        return events


# ---- Unified Behavior Engine ------------------------------------------------

class BehaviorEngine:
    """Orchestrates all behavior detectors on every frame update."""

    def __init__(self, zones: Optional[List[Zone]] = None):
        self.zones = zones or []
        self.loitering = LoiteringDetector(self.zones)
        self.crowd = CrowdDensityEstimator(self.zones)
        self.speed = SpeedDirectionAnalyzer()
        self.intrusion = ZoneIntrusionDetector(self.zones)
        self.tailgating = TailgatingDetector(self.zones)
        self._event_log: List[BehaviorEvent] = []

    def process(
        self,
        tracks: List[Dict],
        timestamp: Optional[datetime] = None,
    ) -> List[BehaviorEvent]:
        """Run all detectors and return new events for this frame."""
        ts = timestamp or datetime.utcnow()
        events: List[BehaviorEvent] = []
        events.extend(self.loitering.update(tracks, ts))
        events.extend(self.crowd.update(tracks, ts))
        events.extend(self.speed.update(tracks, ts))
        events.extend(self.speed.detect_stopped_vehicles(tracks, timestamp=ts))
        events.extend(self.intrusion.update(tracks, ts))
        events.extend(self.tailgating.update(tracks, ts))
        self._event_log.extend(events)
        return events

    @property
    def all_events(self) -> List[BehaviorEvent]:
        return list(self._event_log)

    def clear_log(self):
        self._event_log.clear()


__all__ = [
    "BehaviorType",
    "BehaviorEvent",
    "Zone",
    "LoiteringDetector",
    "CrowdDensityEstimator",
    "SpeedDirectionAnalyzer",
    "ZoneIntrusionDetector",
    "TailgatingDetector",
    "BehaviorEngine",
]
