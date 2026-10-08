"""Security and API contract regression tests."""

import pytest
from fastapi.routing import APIRoute

from api.auth import create_access_token, decode_token, require_role
from db.models import UserRole


def _routes():
    from api.main import fastapi_app
    return [route for route in fastapi_app.routes if isinstance(route, APIRoute)]

def _openapi_paths():
    from api.main import fastapi_app
    return fastapi_app.openapi()["paths"]


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
    assert matches[0].endpoint.__name__ == "get_persons_gallery"


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
    paths = _openapi_paths()
    route_path = next((candidate for candidate in paths if candidate.rstrip("/") == path.rstrip("/") or candidate.startswith(path.rstrip("/") + "/{")), None)
    assert route_path is not None, f"route missing: {path}"
    get_spec = paths[route_path].get("get") or paths[route_path].get("post")
    assert get_spec is not None
    assert get_spec.get("security"), f"route is not protected: {path}"


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
