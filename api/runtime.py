"""Runtime configuration and production-safety validation."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    secret_key: str
    fernet_key: str
    cors_origins: tuple[str, ...]
    db_url: str
    redis_url: str
    token_expire_minutes: int

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def allow_all_origins(self) -> bool:
        return self.cors_origins == ("*",)


def load_config() -> RuntimeConfig:
    environment = os.getenv("SENTINELFORGE_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    secret_key = os.getenv("SECRET_KEY", "")
    fernet_key = os.getenv("FERNET_KEY", "")
    db_url = os.getenv("DB_URL", "postgresql+asyncpg://sentinelforge:sentinelforge@localhost:5432/sentinelforge")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    raw_origins = os.getenv("CORS_ORIGINS", "*")
    origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip()) or ("*",)
    token_expire_minutes = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))

    if environment in {"production", "prod"}:
        if not secret_key or len(secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be set to at least 32 characters in production")
        if not fernet_key:
            raise RuntimeError("FERNET_KEY must be set in production; generated keys are not persistent")
        if origins == ("*",):
            raise RuntimeError("CORS_ORIGINS must explicitly list trusted origins in production")
    else:
        secret_key = secret_key or "development-only-change-me-" + secrets.token_hex(16)
        fernet_key = fernet_key or ""

    return RuntimeConfig(
        environment=environment,
        secret_key=secret_key,
        fernet_key=fernet_key,
        cors_origins=origins,
        db_url=db_url,
        redis_url=redis_url,
        token_expire_minutes=token_expire_minutes,
    )
