"""Privacy endpoint policy and deletion behavior tests."""

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.privacy import forget_person, privacy_policy_metadata, purge_expired_unknown_sightings


@pytest.mark.asyncio
async def test_privacy_policy_is_explicit():
    policy = await privacy_policy_metadata()
    assert policy["unknown_sighting_retention_days"] == 90
    assert policy["person_deletion"] == "permanent"


@pytest.mark.asyncio
async def test_retention_rejects_out_of_range_values():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await purge_expired_unknown_sightings(0, db, {"id": str(uuid4())})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_retention_purge_records_audit_and_count():
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=7)
    db.add = lambda obj: setattr(db, "_audit", obj)
    result = await purge_expired_unknown_sightings(30, db, {"id": str(uuid4()), "username": "admin"})
    assert result["deleted"] == 7
    assert db._audit.action == "privacy_retention_purge"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_forget_person_missing_subject_is_404():
    db = AsyncMock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        await forget_person(uuid4(), db, {"id": str(uuid4()), "username": "admin"})
    assert exc.value.status_code == 404
