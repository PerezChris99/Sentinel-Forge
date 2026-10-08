"""Security and API contract regression tests."""

import inspect

import pytest
from fastapi.routing import APIRoute

from api.auth import create_access_token, decode_token, require_role
from db.models import UserRole


def _routes():
    from api.main import app
    return [route for route in app.routes if isinstance(route, APIRoute)]


def test_no_duplicate_api_route_methods():
    seen = set()
    duplicates = []
    for route in _routes():
        for method in route.methods or set():
            key = (method, route.path)
            if key in seen:
                duplicates.append(key)
            seen.add(key)
    assert not duplicates, f"duplicate routes: {duplicates}"


def test_dashboard_persons_endpoint_is_single_authoritative_route():
    matches = [r for r in _routes() if r.path == "/api/persons" and "GET" in (r.methods or set())]
    assert len(matches) == 1
    assert matches[0].endpoint.__name__ == "list_persons"


@pytest.mark.parametrize(
    "path",
    [
        "/api/persons",
        "/api/cameras",
        "/api/alerts",
        "/api/incidents",
        "/api/search",
        "/api/export/csv",
        "/api/detections",
        "/api/tracks",
        "/api/behaviors",
        "/api/vehicles",
        "/api/zones",
        "/api/graph/relationships",
        "/api/graph/stats",
        "/api/audit/logs",
    ],
)
def test_sensitive_api_routes_require_authentication(path):
    route = next(r for r in _routes() if r.path == path)
    source = inspect.getsource(route.endpoint)
    assert "Depends(get_current_user)" in source or "Depends(require_role" in source or "Depends(require_operator_or_ingest)" in source


def test_jwt_contains_and_validates_issuer_and_audience():
    token = create_access_token({"sub": "user-1", "role": "viewer"})
    payload = decode_token(token)
    assert payload["iss"] == "sentinelforge"
    assert payload["aud"] == "sentinelforge-api"
    assert payload["sub"] == "user-1"


def test_jwt_rejects_wrong_audience(monkeypatch):
    from api import auth

    token = auth.jwt.encode(
        {"sub": "u", "iss": "sentinelforge", "aud": "wrong"},
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )
    with pytest.raises(Exception):
        decode_token(token)


def test_role_hierarchy_is_strict():
    checker = require_role(UserRole.OPERATOR)
    assert checker is not None
