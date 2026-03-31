"""Runtime configuration helpers for the SentinelForge dashboard."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    raw = os.getenv(key)
    if raw is not None:
        return raw
    return default


def _get_bool(key: str, default: bool = False) -> bool:
    raw = _get_env(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class DashboardConfig:
    """Simple container for dashboard-specific environment knobs."""

    api_url: str = os.getenv("DASHBOARD_API_URL", "http://localhost:8000")
    socket_url: str = os.getenv("DASHBOARD_SOCKET_URL", "")
    jwt_token: str = os.getenv("JWT_TOKEN", "demo-token")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "sentinelforge-dashboard")
    jwt_issuer: str = os.getenv("JWT_ISSUER", "sentinelforge-auth")
    use_mocks: bool = _get_bool("SENTINELFORGE_USE_MOCKS", default=True)
    enable_socket_stream: bool = _get_bool("SENTINELFORGE_ENABLE_SOCKET", default=False)
    request_timeout: float = float(_get_env("SENTINELFORGE_API_TIMEOUT", default="5"))
    max_events_cached: int = int(_get_env("SENTINELFORGE_MAX_EVENTS", default="200"))
    verify_tls: bool = _get_bool("SENTINELFORGE_VERIFY_TLS", default=True)

    def optional_token(self) -> Optional[str]:
        token = self.jwt_token.strip()
        return token or None
