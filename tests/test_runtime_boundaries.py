"""Runtime configuration boundary tests."""

import pytest

from api.runtime import load_config


def _set_valid_production(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "s" * 64)
    monkeypatch.setenv("FERNET_KEY", "x" * 44)
    monkeypatch.setenv("CORS_ORIGINS", "https://console.example")
    monkeypatch.setenv("INGEST_API_KEY", "i" * 64)


def test_valid_production_configuration_loads(monkeypatch):
    _set_valid_production(monkeypatch)
    config = load_config()
    assert config.is_production
    assert config.allow_all_origins is False
    assert config.ingest_api_key == "i" * 64


@pytest.mark.parametrize(
    "name,value,match",
    [
        ("SECRET_KEY", "short", "SECRET_KEY"),
        ("FERNET_KEY", "", "FERNET_KEY"),
        ("INGEST_API_KEY", "short", "INGEST_API_KEY"),
    ],
)
def test_production_secret_boundaries(monkeypatch, name, value, match):
    _set_valid_production(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=match):
        load_config()


def test_production_rejects_empty_origin_list(monkeypatch):
    _set_valid_production(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        load_config()


def test_non_production_allows_wildcard_cors(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    config = load_config()
    assert config.allow_all_origins is True
