import pytest

from api.runtime import load_config


def test_development_config_generates_safe_nonempty_secret(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    config = load_config()
    assert len(config.secret_key) >= 32
    assert config.is_production is False


def test_production_requires_persistent_secrets(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_config()


def test_production_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("FERNET_KEY", "x" * 44)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        load_config()
