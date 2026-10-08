"""Dashboard-to-API contract tests that do not require a live backend."""

from dashboard.services.api_client import SentinelForgeAPI
from dashboard.services.config import DashboardConfig


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _client():
    return SentinelForgeAPI(DashboardConfig(api_url="http://example.test", use_mocks=False))


def test_overview_uses_existing_backend_route(monkeypatch):
    client = _client()
    seen = {}

    def fake_get(path, **kwargs):
        seen["path"] = path
        return {"total_persons": 2}

    monkeypatch.setattr(client, "_get", fake_get)
    assert client.fetch_overview_stats()["total_persons"] == 2
    assert seen["path"] == "api/stats/overview"


def test_person_client_accepts_backend_list(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_get", lambda path, **kwargs: [{"id": "p1", "name": "Alice"}])
    assert client.fetch_persons() == [{"id": "p1", "name": "Alice"}]


def test_person_timeline_filters_recent_feed(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, **kwargs: [
            {"id": "s1", "person_id": "p1"},
            {"id": "s2", "person_id": "p2"},
        ],
    )
    assert client.fetch_person_timeline("p1") == [{"id": "s1", "person_id": "p1"}]
    assert client.fetch_person_timeline(None) == []
