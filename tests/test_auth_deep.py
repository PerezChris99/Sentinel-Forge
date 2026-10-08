"""Authentication, password, JWT, and role boundary tests."""

from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import (
    create_access_token,
    decode_token,
    get_current_user,
    get_password_hash,
    require_operator_or_ingest,
    require_role,
    verify_password,
)
from db.models import UserRole


def test_password_hash_round_trip_and_rejection():
    hashed = get_password_hash("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_expired_token_is_rejected():
    token = create_access_token({"sub": "u", "role": "viewer"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_requires_subject():
    token = create_access_token({"role": "viewer"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException):
        await get_current_user(credentials)


@pytest.mark.asyncio
async def test_role_checker_allows_higher_roles_and_rejects_lower():
    admin_checker = require_role(UserRole.ADMIN)
    assert (await admin_checker({"role": "admin", "id": "u"}))["role"] == "admin"
    with pytest.raises(HTTPException) as exc:
        await admin_checker({"role": "operator", "id": "u"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_operator_or_ingest_accepts_operator_and_rejects_viewer(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "development")
    creds = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=create_access_token({"sub": "op", "role": "operator"}),
    )
    class Request:
        headers = {}
    result = await require_operator_or_ingest(Request(), creds)
    assert result["role"] == "operator"

    viewer = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=create_access_token({"sub": "v", "role": "viewer"}),
    )
    with pytest.raises(HTTPException) as exc:
        await require_operator_or_ingest(Request(), viewer)
    assert exc.value.status_code == 403
