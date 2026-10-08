"""
Knowledge Graph Engine for SentinelForge.

Models entity-entity relationships and provides graph analysis:
- Entity nodes: person, vehicle, incident, camera, zone, track
- Typed edges: seen_with, co_located, involved_in, entered_zone, etc.
- Temporal correlation: entities co-occurring within a time window
- Path finding: shortest path / "N degrees of separation"
- Cluster detection: connected components
- Link strength: weighted edge aggregation over time

Pure Python + numpy — no Neo4j or external graph DB required.
Uses PostgreSQL via EntityRelationship table for persistence.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

LOGGER = logging.getLogger(__name__)


# ---- Enums ------------------------------------------------------------------

class EntityType(str, Enum):
    PERSON = "person"
    VEHICLE = "vehicle"
    INCIDENT = "incident"
    CAMERA = "camera"
    ZONE = "zone"
    TRACK = "track"


class RelationType(str, Enum):
    SEEN_WITH = "seen_with"            # Two entities observed at same time/place
    CO_LOCATED = "co_located"          # Two entities in same zone
    INVOLVED_IN = "involved_in"        # Entity linked to an incident
    ASSOCIATED_WITH = "associated_with"  # General association
    ENTERED_ZONE = "entered_zone"      # Entity entered a zone
    OWNS_VEHICLE = "owns_vehicle"      # Person linked to a vehicle
    DETECTED_BY = "detected_by"        # Entity detected by camera
    FOLLOWS = "follows"                # One entity follows another (track)
    TEMPORAL = "temporal"              # Co-occurrence in a time window


# ---- Data classes -----------------------------------------------------------

@dataclass
class Entity:
    """A node in the knowledge graph."""
    entity_id: str
    entity_type: EntityType
    label: str = ""
    properties: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.entity_type.value}:{self.entity_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["key"] = self.key
        return d


@dataclass
class Relationship:
    """An edge in the knowledge graph."""
    source_key: str            # "person:abc123"
    target_key: str            # "vehicle:xyz789"
    relation_type: RelationType
    weight: float = 1.0
    timestamp: Optional[datetime] = None
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relation_type"] = self.relation_type.value
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return d


@dataclass
class PathResult:
    """Result of a shortest-path query."""
    source: str
    target: str
    path: List[str]          # ordered list of entity keys
    edges: List[dict]        # edge info for each hop
    hops: int
    total_weight: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClusterResult:
    """A connected component / cluster of entities."""
    cluster_id: int
    entities: List[str]
    size: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Knowledge Graph Engine -------------------------------------------------

class KnowledgeGraphEngine:
    """In-memory graph with persistent backing via DB records.

    Maintains an adjacency list for fast traversal.
    """

    def __init__(self):
        # Entity registry: key -> Entity
        self.entities: Dict[str, Entity] = {}
        # Adjacency list: key -> [(target_key, Relationship)]
        self._adj: Dict[str, List[Tuple[str, Relationship]]] = defaultdict(list)
        # Reverse adjacency for bidirectional traversal
        self._adj_rev: Dict[str, List[Tuple[str, Relationship]]] = defaultdict(list)
        # All relationships for serialization
        self._relationships: List[Relationship] = []

    # ---- Entity management --------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        self.entities[entity.key] = entity
        return entity

    def get_entity(self, key: str) -> Optional[Entity]:
        return self.entities.get(key)

    def remove_entity(self, key: str) -> bool:
        if key not in self.entities:
            return False
        del self.entities[key]
        # Remove all edges involving this entity
        self._adj.pop(key, None)
        self._adj_rev.pop(key, None)
        self._relationships = [
            r for r in self._relationships
            if r.source_key != key and r.target_key != key
        ]
        for k in list(self._adj.keys()):
            self._adj[k] = [(t, r) for t, r in self._adj[k] if t != key]
        for k in list(self._adj_rev.keys()):
            self._adj_rev[k] = [(t, r) for t, r in self._adj_rev[k] if t != key]
        return True

    def list_entities(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
    ) -> List[Entity]:
        result = list(self.entities.values())
        if entity_type:
            result = [e for e in result if e.entity_type == entity_type]
        return result[:limit]

    # ---- Relationship management --------------------------------------------

    def add_relationship(self, rel: Relationship) -> Relationship:
        self._adj[rel.source_key].append((rel.target_key, rel))
        self._adj_rev[rel.target_key].append((rel.source_key, rel))
        self._relationships.append(rel)
        # Ensure both entities are registered
        for key in (rel.source_key, rel.target_key):
            if key not in self.entities:
                parts = key.split(":", 1)
                if len(parts) == 2:
                    self.add_entity(Entity(
                        entity_id=parts[1],
                        entity_type=EntityType(parts[0]),
                        label=parts[1],
                    ))
        return rel

    def get_relationships(
        self,
        entity_key: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both",  # "outgoing" | "incoming" | "both"
    ) -> List[Relationship]:
        results: List[Relationship] = []
        if direction in ("outgoing", "both"):
            for _, rel in self._adj.get(entity_key, []):
                if relation_type is None or rel.relation_type == relation_type:
                    results.append(rel)
        if direction in ("incoming", "both"):
            for _, rel in self._adj_rev.get(entity_key, []):
                if relation_type is None or rel.relation_type == relation_type:
                    results.append(rel)
        return results

    def all_relationships(self) -> List[Relationship]:
        return list(self._relationships)

    # ---- Neighbors ----------------------------------------------------------

    def neighbors(
        self,
        entity_key: str,
        max_depth: int = 1,
        relation_type: Optional[RelationType] = None,
    ) -> Dict[str, int]:
        """BFS to find all entities within max_depth hops. Returns {key: depth}."""
        visited: Dict[str, int] = {entity_key: 0}
        queue: deque = deque([(entity_key, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for target, rel in self._adj.get(current, []):
                if relation_type and rel.relation_type != relation_type:
                    continue
                if target not in visited:
                    visited[target] = depth + 1
                    queue.append((target, depth + 1))
            for target, rel in self._adj_rev.get(current, []):
                if relation_type and rel.relation_type != relation_type:
                    continue
                if target not in visited:
                    visited[target] = depth + 1
                    queue.append((target, depth + 1))

        visited.pop(entity_key, None)
        return visited

    # ---- Shortest path (BFS, unweighted) ------------------------------------

    def shortest_path(
        self,
        source_key: str,
        target_key: str,
        max_depth: int = 6,
    ) -> Optional[PathResult]:
        """BFS shortest path between two entities (undirected edges)."""
        if source_key == target_key:
            return PathResult(source_key, target_key, [source_key], [], 0, 0.0)
        if source_key not in self.entities or target_key not in self.entities:
            return None

        visited: Dict[str, Optional[str]] = {source_key: None}
        edge_used: Dict[str, Optional[Relationship]] = {source_key: None}
        queue: deque = deque([(source_key, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Explore both directions
            adj_edges = (
                [(t, r) for t, r in self._adj.get(current, [])]
                + [(t, r) for t, r in self._adj_rev.get(current, [])]
            )
            for neighbor, rel in adj_edges:
                if neighbor not in visited:
                    visited[neighbor] = current
                    edge_used[neighbor] = rel
                    if neighbor == target_key:
                        # Reconstruct path
                        path: List[str] = []
                        edges: List[dict] = []
                        total_weight = 0.0
                        node = target_key
                        while node is not None:
                            path.append(node)
                            r = edge_used.get(node)
                            if r:
                                edges.append(r.to_dict())
                                total_weight += r.weight
                            node = visited.get(node)
                        path.reverse()
                        edges.reverse()
                        return PathResult(
                            source=source_key,
                            target=target_key,
                            path=path,
                            edges=edges,
                            hops=len(path) - 1,
                            total_weight=total_weight,
                        )
                    queue.append((neighbor, depth + 1))

        return None  # No path found within max_depth

    # ---- Connected components -----------------------------------------------

    def connected_components(self) -> List[ClusterResult]:
        """Find all connected components (clusters) in the graph."""
        visited: Set[str] = set()
        clusters: List[ClusterResult] = []
        cluster_id = 0

        for key in self.entities:
            if key in visited:
                continue
            # BFS from this node
            component: List[str] = []
            queue: deque = deque([key])
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                component.append(node)
                for target, _ in self._adj.get(node, []):
                    if target not in visited:
                        queue.append(target)
                for target, _ in self._adj_rev.get(node, []):
                    if target not in visited:
                        queue.append(target)

            clusters.append(ClusterResult(
                cluster_id=cluster_id,
                entities=component,
                size=len(component),
            ))
            cluster_id += 1

        return sorted(clusters, key=lambda c: -c.size)

    # ---- Temporal correlation -----------------------------------------------

    def find_temporal_correlations(
        self,
        entity_key: str,
        time_window: timedelta = timedelta(minutes=5),
        min_co_occurrences: int = 2,
    ) -> List[Dict]:
        """Find entities that frequently appear near this entity within a time window.

        Based on relationship timestamps.
        """
        # Gather all timestamps for this entity's relations
        entity_times: List[Tuple[str, datetime]] = []
        for target, rel in self._adj.get(entity_key, []):
            if rel.timestamp:
                entity_times.append((target, rel.timestamp))
        for target, rel in self._adj_rev.get(entity_key, []):
            if rel.timestamp:
                entity_times.append((target, rel.timestamp))

        if not entity_times:
            return []

        # For each other entity, check timestamp proximity
        co_counts: Dict[str, int] = defaultdict(int)
        for other_key in self.entities:
            if other_key == entity_key:
                continue
            other_times: List[datetime] = []
            for _, rel in self._adj.get(other_key, []):
                if rel.timestamp:
                    other_times.append(rel.timestamp)
            for _, rel in self._adj_rev.get(other_key, []):
                if rel.timestamp:
                    other_times.append(rel.timestamp)

            for _, et in entity_times:
                for ot in other_times:
                    if abs((et - ot).total_seconds()) <= time_window.total_seconds():
                        co_counts[other_key] += 1
                        break  # count once per entity-time pair

        results = [
            {"entity_key": k, "co_occurrences": v}
            for k, v in co_counts.items()
            if v >= min_co_occurrences
        ]
        return sorted(results, key=lambda x: -x["co_occurrences"])

    # ---- Link strength ------------------------------------------------------

    def link_strength(self, key_a: str, key_b: str) -> Dict:
        """Calculate aggregate relationship strength between two entities."""
        direct_edges = []
        total_weight = 0.0
        for target, rel in self._adj.get(key_a, []):
            if target == key_b:
                direct_edges.append(rel)
                total_weight += rel.weight
        for target, rel in self._adj_rev.get(key_a, []):
            if target == key_b:
                direct_edges.append(rel)
                total_weight += rel.weight

        return {
            "entity_a": key_a,
            "entity_b": key_b,
            "direct_edges": len(direct_edges),
            "total_weight": total_weight,
            "relation_types": list({r.relation_type.value for r in direct_edges}),
        }

    # ---- Auto-link from sightings -------------------------------------------

    def auto_link_co_sightings(
        self,
        sightings: List[Dict],
        time_window: timedelta = timedelta(minutes=5),
    ) -> List[Relationship]:
        """Given a list of sighting dicts, auto-create SEEN_WITH edges for
        entities detected within the same time window at the same camera.

        Each sighting dict should have: person_id, camera_id, timestamp.
        """
        new_rels: List[Relationship] = []
        # Group by camera
        by_camera: Dict[str, List[Dict]] = defaultdict(list)
        for s in sightings:
            cam = s.get("camera_id")
            if cam:
                by_camera[cam].append(s)

        for cam, cam_sightings in by_camera.items():
            cam_sightings.sort(key=lambda x: x.get("timestamp", datetime.min))
            for i, s1 in enumerate(cam_sightings):
                pid1 = s1.get("person_id")
                ts1 = s1.get("timestamp")
                if not pid1 or not ts1:
                    continue
                key1 = f"person:{pid1}"
                for j in range(i + 1, len(cam_sightings)):
                    s2 = cam_sightings[j]
                    pid2 = s2.get("person_id")
                    ts2 = s2.get("timestamp")
                    if not pid2 or not ts2 or pid1 == pid2:
                        continue
                    if (ts2 - ts1).total_seconds() > time_window.total_seconds():
                        break
                    key2 = f"person:{pid2}"
                    rel = Relationship(
                        source_key=key1,
                        target_key=key2,
                        relation_type=RelationType.SEEN_WITH,
                        weight=1.0,
                        timestamp=ts1,
                        properties={"camera_id": cam},
                    )
                    self.add_relationship(rel)
                    new_rels.append(rel)

        LOGGER.info("Auto-linked %d co-sighting relationships", len(new_rels))
        return new_rels

    # ---- Stats / export -----------------------------------------------------

    def stats(self) -> Dict:
        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self._relationships),
            "entity_types": dict(
                defaultdict(int, {
                    e.entity_type.value: sum(
                        1 for x in self.entities.values()
                        if x.entity_type == e.entity_type
                    )
                    for e in self.entities.values()
                })
            ),
            "relation_types": dict(
                defaultdict(int, {
                    r.relation_type.value: sum(
                        1 for x in self._relationships
                        if x.relation_type == r.relation_type
                    )
                    for r in self._relationships
                })
            ),
        }

    def export_graph(self) -> Dict:
        """Export full graph as JSON-serializable dict."""
        return {
            "entities": [e.to_dict() for e in self.entities.values()],
            "relationships": [r.to_dict() for r in self._relationships],
            "stats": self.stats(),
        }

    def clear(self):
        self.entities.clear()
        self._adj.clear()
        self._adj_rev.clear()
        self._relationships.clear()


__all__ = [
    "EntityType",
    "RelationType",
    "Entity",
    "Relationship",
    "PathResult",
    "ClusterResult",
    "KnowledgeGraphEngine",
]
