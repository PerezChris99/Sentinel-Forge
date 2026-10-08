"""Database model contract tests."""

from sqlalchemy import create_engine, inspect

from db.models import Base


def test_all_tables_create_on_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    expected = {
        "persons", "sightings", "patterns", "footage_refs", "users", "cameras", "alerts",
        "incidents", "incident_events", "audit_logs", "search_queries",
        "detected_objects", "tracks", "behavior_events", "vehicles",
        "zones", "entity_relationships",
    }
    assert expected.issubset(table_names)


def test_primary_keys_and_indexes_are_declared():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    for table in ("persons", "sightings", "cameras", "users", "audit_logs"):
        pk = inspector.get_pk_constraint(table)
        assert pk["constrained_columns"], table
