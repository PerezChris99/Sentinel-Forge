"""HTTP-level authentication and security-header regression tests."""

from fastapi.testclient import TestClient


def test_public_health_and_metrics_are_available():
    from api.main import app

    with TestClient(app) as client:
        live = client.get("/live")
        metrics = client.get("/metrics")
        assert live.status_code == 200
        assert metrics.status_code == 200
        assert "sentinelforge_up 1" in metrics.text


def test_sensitive_routes_reject_anonymous_clients():
    from api.main import app

    with TestClient(app) as client:
        for path in ("/api/persons", "/api/cameras", "/api/alerts", "/api/detections", "/api/graph/stats"):
            response = client.get(path)
            assert response.status_code == 401, path


def test_security_headers_are_present():
    from api.main import app

    with TestClient(app) as client:
        response = client.get("/live")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "strict-origin" in response.headers["referrer-policy"]
