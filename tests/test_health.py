from fastapi.testclient import TestClient


def test_liveness_endpoint():
    from api.main import app

    with TestClient(app) as client:
        response = client.get("/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


def test_root_reports_api():
    from api.main import app

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "SentinelForge API" in response.json()["message"]
