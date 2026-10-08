"""Direct CRUD-router smoke coverage using a deterministic async DB stub."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from api import extended


class Result:
    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def scalar(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def one_or_none(self):
        return None

    def all_rows(self):
        return []


class DB:
    def __init__(self):
        self.added = []

    async def execute(self, _statement):
        return Result()

    async def get(self, *_args):
        return None

    def add(self, value):
        self.added.append(value)

    async def delete(self, _value):
        return None

    async def commit(self):
        return None

    async def refresh(self, _value):
        return None


USER = {"id": str(uuid4()), "username": "tester", "role": "admin"}


@pytest.mark.asyncio
async def test_collection_read_endpoints_handle_empty_database():
    db = DB()
    assert await extended.list_cameras(db=db, user=USER) == []
    assert await extended.list_persons(db=db, user=USER) == []
    assert await extended.list_alerts(db=db, limit=100, user=USER) == []
    assert await extended.list_incidents(db=db, limit=50, user=USER) == []
    assert await extended.search_all("anything", db=db, limit=50, user=USER) is not None
    assert await extended.list_detections(db=db, limit=100, offset=0, user=USER) == []
    assert await extended.list_tracks(db=db, limit=100, offset=0, user=USER) == []
    assert await extended.list_behavior_events(db=db, limit=100, offset=0, user=USER) == []
    assert await extended.list_vehicles(db=db, limit=100, offset=0, user=USER) == []
    assert await extended.search_vehicle_by_plate("UAX", db=db, limit=50, user=USER) == []
    assert await extended.list_zones(db=db, limit=100, offset=0, user=USER) == []
    assert await extended.list_relationships(db=db, limit=100, offset=0, user=USER) == []


@pytest.mark.asyncio
async def test_analytics_and_graph_empty_state_endpoints():
    db = DB()
    behavior = await extended.behavior_stats(db=db, hours=24)
    graph = await extended.graph_stats(db=db, user=USER)
    links = await extended.get_entity_links("person", "p1", db=db, limit=100)
    with pytest.raises(HTTPException) as exc:
        await extended.zone_occupancy("zone-1", db=db)
    assert exc.value.status_code == 404
    assert behavior is not None
    assert graph["total_relationships"] == 0
    assert links == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler,args",
    [
        (extended.get_camera, {"camera_id": "missing"}),
        (extended.get_person, {"person_id": uuid4()}),
        (extended.get_incident, {"incident_id": uuid4()}),
        (extended.get_detection, {"detection_id": uuid4()}),
        (extended.get_track, {"track_label": "missing"}),
        (extended.get_zone, {"zone_id": "missing"}),
    ],
)
async def test_entity_getters_return_404_for_missing_records(handler, args):
    with pytest.raises(HTTPException) as exc:
        await handler(db=DB(), user=USER, **args)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_policy_protected_mutations_reject_missing_records():
    with pytest.raises(HTTPException) as exc:
        await extended.acknowledge_alert(uuid4(), db=DB(), user=USER)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await extended.deactivate_track("missing", db=DB(), user=USER)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await extended.delete_zone("missing", db=DB(), user=USER)
    assert exc.value.status_code == 404
