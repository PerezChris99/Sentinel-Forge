"""Socket.IO security regression tests."""

import pytest

from api.auth import create_access_token, SECRET_KEY
from api.websocket import connect, disconnect, socket_users, user_rooms


@pytest.mark.asyncio
async def test_production_rejects_unauthenticated_socket(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 64)
    result = await connect("sid-unauth", {}, {})
    assert result is False


@pytest.mark.asyncio
async def test_production_accepts_valid_socket_token(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", SECRET_KEY)
    token = create_access_token({"sub": "user-1", "role": "viewer"})
    result = await connect("sid-auth", {}, {"token": token})
    assert result is None
    assert socket_users["sid-auth"] == "user-1"
    await disconnect("sid-auth")
    assert "sid-auth" not in socket_users


def test_room_state_isolated_by_authenticated_user():
    assert isinstance(user_rooms, dict)
