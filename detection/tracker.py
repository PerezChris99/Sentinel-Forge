"""
Multi-object tracker with IoU + optional appearance (ReID) matching,
cross-camera track reconciliation, and dwell-time/velocity metadata.

The tracker exposes ``Tracker.update(detections, timestamp)`` where
``detections`` is a list of dicts with ``bbox`` (x1,y1,x2,y2) and optional
``class_name`` / ``embedding``.  It returns a list of active tracks.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from uuid import uuid4

import numpy as np

LOGGER = logging.getLogger(__name__)


# ---- geometry helpers -------------------------------------------------------

def _iou(boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interW = max(0, xB - xA + 1)
    interH = max(0, yB - yA + 1)
    interArea = interW * interH

    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    denom = float(boxAArea + boxBArea - interArea)
    if denom <= 0:
        return 0.0
    return interArea / denom


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _bbox_center(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


# ---- Tracker ----------------------------------------------------------------

class Tracker:
    """IoU + optional ReID embedding tracker with velocity and dwell time."""

    def __init__(
        self,
        iou_threshold: float = 0.3,
        reid_threshold: float = 0.7,
        max_lost_frames: int = 5,
        use_reid: bool = True,
    ):
        self.iou_threshold = iou_threshold
        self.reid_threshold = reid_threshold
        self.max_lost_frames = max_lost_frames
        self.use_reid = use_reid
        self.tracks: Dict[str, Dict] = {}
        self._next_numeric = 1

    # -- id helpers -----------------------------------------------------------

    def _new_track_id(self) -> str:
        tid = f"t{self._next_numeric:06d}-{uuid4().hex[:6]}"
        self._next_numeric += 1
        return tid

    # -- core update ----------------------------------------------------------

    def update(
        self,
        detections: List[Dict],
        timestamp: Optional[datetime] = None,
        camera_id: Optional[str] = None,
    ) -> List[Dict]:
        """Match detections to existing tracks; return active tracks.

        Each detection dict may include:
        - ``bbox``: [x1,y1,x2,y2]  (required)
        - ``class_name``: str
        - ``embedding``: list[float] or np.ndarray  (optional, for ReID)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        det_bboxes = [tuple(d["bbox"]) for d in detections]

        # First frame — seed tracks
        if not self.tracks:
            for det, bbox in zip(detections, det_bboxes):
                self._create_track(det, bbox, timestamp, camera_id)
            return self._all_formatted()

        # Build cost matrix (higher = better match)
        track_ids = list(self.tracks.keys())
        cost = np.zeros((len(track_ids), len(det_bboxes)), dtype=float)
        for i, tid in enumerate(track_ids):
            tb = self.tracks[tid]["bbox"]
            te = self.tracks[tid].get("embedding")
            for j, db in enumerate(det_bboxes):
                iou_score = _iou(tb, db)
                reid_score = 0.0
                if self.use_reid and te is not None:
                    de = detections[j].get("embedding")
                    if de is not None:
                        de_arr = np.asarray(de, dtype=float)
                        reid_score = _cosine_sim(np.asarray(te, dtype=float), de_arr)
                # Weighted combination
                cost[i, j] = 0.6 * iou_score + 0.4 * reid_score if reid_score > 0 else iou_score

        # Greedy matching
        assigned_tracks: set = set()
        assigned_dets: set = set()

        while True:
            if cost.size == 0:
                break
            idx = np.unravel_index(np.argmax(cost), cost.shape)
            best = cost[idx]
            if best < self.iou_threshold:
                break
            i, j = int(idx[0]), int(idx[1])
            tid = track_ids[i]
            det = detections[j]
            prev_center = _bbox_center(self.tracks[tid]["bbox"])
            new_center = _bbox_center(det_bboxes[j])

            # Update track state
            self.tracks[tid]["bbox"] = det_bboxes[j]
            self.tracks[tid]["class_name"] = det.get("class_name")
            self.tracks[tid]["last_seen"] = timestamp
            self.tracks[tid]["lost"] = 0
            if det.get("embedding") is not None:
                self.tracks[tid]["embedding"] = list(det["embedding"]) if not isinstance(det["embedding"], list) else det["embedding"]
            # Velocity (pixels/frame)
            dx = new_center[0] - prev_center[0]
            dy = new_center[1] - prev_center[1]
            self.tracks[tid]["velocity"] = (dx, dy)
            self.tracks[tid]["speed"] = math.hypot(dx, dy)
            if camera_id:
                self.tracks[tid].setdefault("cameras_seen", set()).add(camera_id)

            assigned_tracks.add(tid)
            assigned_dets.add(j)
            cost[i, :] = -1
            cost[:, j] = -1

        # Unmatched detections → new tracks
        for j, det in enumerate(detections):
            if j in assigned_dets:
                continue
            self._create_track(det, det_bboxes[j], timestamp, camera_id)

        # Age unmatched tracks
        for tid in list(self.tracks.keys()):
            if tid in assigned_tracks:
                continue
            self.tracks[tid]["lost"] += 1
            if self.tracks[tid]["lost"] > self.max_lost_frames:
                LOGGER.debug("Pruning track %s after %d lost frames", tid, self.tracks[tid]["lost"])
                del self.tracks[tid]

        return self._all_formatted()

    # -- cross-camera ReID ----------------------------------------------------

    def reconcile_cross_camera(
        self,
        other_tracker: "Tracker",
        similarity_threshold: float = 0.75,
    ) -> List[Tuple[str, str, float]]:
        """Compare active tracks between two trackers (different cameras).

        Returns list of (track_id_self, track_id_other, similarity).
        """
        matches: List[Tuple[str, str, float]] = []
        for tid_a, ta in self.tracks.items():
            ea = ta.get("embedding")
            if ea is None:
                continue
            ea_arr = np.asarray(ea, dtype=float)
            for tid_b, tb in other_tracker.tracks.items():
                eb = tb.get("embedding")
                if eb is None:
                    continue
                sim = _cosine_sim(ea_arr, np.asarray(eb, dtype=float))
                if sim >= similarity_threshold:
                    matches.append((tid_a, tid_b, sim))
        return matches

    # -- helpers --------------------------------------------------------------

    def _create_track(self, det: Dict, bbox: tuple, ts: datetime, camera_id: Optional[str]):
        tid = self._new_track_id()
        emb = det.get("embedding")
        self.tracks[tid] = {
            "bbox": bbox,
            "class_name": det.get("class_name"),
            "last_seen": ts,
            "first_seen": ts,
            "lost": 0,
            "embedding": list(emb) if emb is not None else None,
            "velocity": (0.0, 0.0),
            "speed": 0.0,
            "cameras_seen": {camera_id} if camera_id else set(),
        }

    def _all_formatted(self) -> List[Dict]:
        return [self._format_track(tid, v) for tid, v in self.tracks.items()]

    def _format_track(self, tid: str, data: Dict) -> Dict:
        dwell = 0.0
        if data.get("first_seen") and data.get("last_seen"):
            dwell = (data["last_seen"] - data["first_seen"]).total_seconds()
        return {
            "track_id": tid,
            "bbox": list(data["bbox"]),
            "class_name": data.get("class_name"),
            "last_seen": data["last_seen"].isoformat() if data.get("last_seen") else None,
            "first_seen": data["first_seen"].isoformat() if data.get("first_seen") else None,
            "velocity": list(data.get("velocity", (0, 0))),
            "speed": data.get("speed", 0.0),
            "dwell_seconds": dwell,
            "cameras_seen": list(data.get("cameras_seen", [])),
            "has_embedding": data.get("embedding") is not None,
        }


__all__ = ["Tracker", "_iou", "_cosine_sim"]
