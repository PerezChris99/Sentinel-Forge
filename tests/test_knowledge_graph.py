"""Tests for the Knowledge Graph Engine."""
from datetime import datetime, timedelta

from analytics.knowledge_graph import (
    KnowledgeGraphEngine,
    Entity,
    EntityType,
    Relationship,
    RelationType,
)


def _engine_with_triangle():
    """Create a graph: A --seen_with--> B --co_located--> C."""
    engine = KnowledgeGraphEngine()
    engine.add_entity(Entity("p1", EntityType.PERSON, "Alice"))
    engine.add_entity(Entity("p2", EntityType.PERSON, "Bob"))
    engine.add_entity(Entity("v1", EntityType.VEHICLE, "Red Car"))

    ts = datetime(2026, 3, 1, 12, 0, 0)
    engine.add_relationship(Relationship(
        source_key="person:p1", target_key="person:p2",
        relation_type=RelationType.SEEN_WITH, weight=1.0, timestamp=ts,
    ))
    engine.add_relationship(Relationship(
        source_key="person:p2", target_key="vehicle:v1",
        relation_type=RelationType.CO_LOCATED, weight=2.0, timestamp=ts,
    ))
    return engine


class TestEntityManagement:
    def test_add_and_get(self):
        engine = KnowledgeGraphEngine()
        e = engine.add_entity(Entity("p1", EntityType.PERSON, "Alice"))
        assert engine.get_entity("person:p1").label == "Alice"

    def test_remove(self):
        engine = KnowledgeGraphEngine()
        engine.add_entity(Entity("p1", EntityType.PERSON))
        assert engine.remove_entity("person:p1") is True
        assert engine.get_entity("person:p1") is None

    def test_list_by_type(self):
        engine = KnowledgeGraphEngine()
        engine.add_entity(Entity("p1", EntityType.PERSON))
        engine.add_entity(Entity("v1", EntityType.VEHICLE))
        assert len(engine.list_entities(EntityType.PERSON)) == 1


class TestRelationships:
    def test_add_and_get(self):
        engine = _engine_with_triangle()
        rels = engine.get_relationships("person:p1")
        assert len(rels) >= 1

    def test_auto_creates_entities(self):
        engine = KnowledgeGraphEngine()
        engine.add_relationship(Relationship(
            source_key="person:x1", target_key="camera:c1",
            relation_type=RelationType.DETECTED_BY,
        ))
        assert engine.get_entity("person:x1") is not None
        assert engine.get_entity("camera:c1") is not None

    def test_direction_filter(self):
        engine = _engine_with_triangle()
        out = engine.get_relationships("person:p1", direction="outgoing")
        inc = engine.get_relationships("person:p1", direction="incoming")
        assert len(out) >= 1
        assert len(inc) == 0

    def test_relation_type_filter(self):
        engine = _engine_with_triangle()
        rels = engine.get_relationships(
            "person:p2", relation_type=RelationType.SEEN_WITH
        )
        assert all(r.relation_type == RelationType.SEEN_WITH for r in rels)


class TestNeighbors:
    def test_depth_1(self):
        engine = _engine_with_triangle()
        n = engine.neighbors("person:p1", max_depth=1)
        assert "person:p2" in n
        assert "vehicle:v1" not in n

    def test_depth_2(self):
        engine = _engine_with_triangle()
        n = engine.neighbors("person:p1", max_depth=2)
        assert "person:p2" in n
        assert "vehicle:v1" in n
        assert n["vehicle:v1"] == 2


class TestShortestPath:
    def test_direct_path(self):
        engine = _engine_with_triangle()
        path = engine.shortest_path("person:p1", "person:p2")
        assert path is not None
        assert path.hops == 1
        assert path.path == ["person:p1", "person:p2"]

    def test_two_hop_path(self):
        engine = _engine_with_triangle()
        path = engine.shortest_path("person:p1", "vehicle:v1")
        assert path is not None
        assert path.hops == 2

    def test_no_path(self):
        engine = KnowledgeGraphEngine()
        engine.add_entity(Entity("p1", EntityType.PERSON))
        engine.add_entity(Entity("p2", EntityType.PERSON))
        path = engine.shortest_path("person:p1", "person:p2")
        assert path is None

    def test_same_entity(self):
        engine = _engine_with_triangle()
        path = engine.shortest_path("person:p1", "person:p1")
        assert path is not None
        assert path.hops == 0

    def test_nonexistent_entity(self):
        engine = _engine_with_triangle()
        assert engine.shortest_path("person:p1", "person:ghost") is None


class TestConnectedComponents:
    def test_single_component(self):
        engine = _engine_with_triangle()
        clusters = engine.connected_components()
        assert len(clusters) == 1
        assert clusters[0].size == 3

    def test_two_components(self):
        engine = _engine_with_triangle()
        engine.add_entity(Entity("isolated", EntityType.CAMERA))
        clusters = engine.connected_components()
        assert len(clusters) == 2

    def test_empty_graph(self):
        engine = KnowledgeGraphEngine()
        assert engine.connected_components() == []


class TestTemporalCorrelation:
    def test_finds_correlated_entities(self):
        engine = KnowledgeGraphEngine()
        ts = datetime(2026, 3, 1, 12, 0, 0)
        engine.add_entity(Entity("p1", EntityType.PERSON))
        engine.add_entity(Entity("p2", EntityType.PERSON))
        engine.add_entity(Entity("c1", EntityType.CAMERA))

        # p1 and p2 both detected by cam within 2 minutes
        engine.add_relationship(Relationship(
            "person:p1", "camera:c1", RelationType.DETECTED_BY, timestamp=ts,
        ))
        engine.add_relationship(Relationship(
            "person:p2", "camera:c1", RelationType.DETECTED_BY,
            timestamp=ts + timedelta(minutes=1),
        ))

        corr = engine.find_temporal_correlations(
            "person:p1", time_window=timedelta(minutes=5), min_co_occurrences=1,
        )
        keys = [c["entity_key"] for c in corr]
        assert "person:p2" in keys or "camera:c1" in keys

    def test_no_correlation_outside_window(self):
        engine = KnowledgeGraphEngine()
        ts = datetime(2026, 3, 1, 12, 0, 0)
        engine.add_entity(Entity("p1", EntityType.PERSON))
        engine.add_entity(Entity("p2", EntityType.PERSON))

        engine.add_relationship(Relationship(
            "person:p1", "camera:c1", RelationType.DETECTED_BY, timestamp=ts,
        ))
        engine.add_relationship(Relationship(
            "person:p2", "camera:c1", RelationType.DETECTED_BY,
            timestamp=ts + timedelta(hours=2),
        ))

        corr = engine.find_temporal_correlations(
            "person:p1", time_window=timedelta(minutes=5), min_co_occurrences=1,
        )
        p2_entries = [c for c in corr if c["entity_key"] == "person:p2"]
        assert len(p2_entries) == 0


class TestLinkStrength:
    def test_direct_strength(self):
        engine = _engine_with_triangle()
        strength = engine.link_strength("person:p1", "person:p2")
        assert strength["direct_edges"] >= 1
        assert strength["total_weight"] >= 1.0

    def test_no_link(self):
        engine = _engine_with_triangle()
        strength = engine.link_strength("person:p1", "vehicle:v1")
        assert strength["direct_edges"] == 0


class TestAutoLinkCoSightings:
    def test_creates_seen_with(self):
        engine = KnowledgeGraphEngine()
        ts = datetime(2026, 3, 1, 12, 0, 0)
        sightings = [
            {"person_id": "p1", "camera_id": "cam1", "timestamp": ts},
            {"person_id": "p2", "camera_id": "cam1", "timestamp": ts + timedelta(minutes=1)},
            {"person_id": "p3", "camera_id": "cam1", "timestamp": ts + timedelta(minutes=2)},
        ]
        rels = engine.auto_link_co_sightings(sightings, time_window=timedelta(minutes=5))
        assert len(rels) >= 2  # p1-p2, p1-p3 (and possibly p2-p3)

    def test_ignores_different_cameras(self):
        engine = KnowledgeGraphEngine()
        ts = datetime(2026, 3, 1, 12, 0, 0)
        sightings = [
            {"person_id": "p1", "camera_id": "cam1", "timestamp": ts},
            {"person_id": "p2", "camera_id": "cam2", "timestamp": ts},
        ]
        rels = engine.auto_link_co_sightings(sightings)
        assert len(rels) == 0


class TestStatsAndExport:
    def test_stats(self):
        engine = _engine_with_triangle()
        s = engine.stats()
        assert s["total_entities"] == 3
        assert s["total_relationships"] == 2

    def test_export_graph(self):
        engine = _engine_with_triangle()
        g = engine.export_graph()
        assert len(g["entities"]) == 3
        assert len(g["relationships"]) == 2
        assert "stats" in g

    def test_clear(self):
        engine = _engine_with_triangle()
        engine.clear()
        assert engine.stats()["total_entities"] == 0
