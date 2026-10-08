"""Celery task contract tests."""

from api.tasks import send_alfie_webhook


def test_alfie_task_is_safe_when_not_configured(monkeypatch):
    monkeypatch.delenv("ALFIE_WEBHOOK_URL", raising=False)
    result = send_alfie_webhook.run({"event": "test"})
    assert result["status"] == "skipped"
    assert "not configured" in result["reason"]
