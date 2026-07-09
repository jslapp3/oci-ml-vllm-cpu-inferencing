"""Configuration for the orchestrator API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class OrchestratorSettings:
    ml_service_base_url: str = field(
        default_factory=lambda: os.getenv("ML_SERVICE_BASE_URL", "http://127.0.0.1:8081")
    )
    ml_service_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("ML_SERVICE_TIMEOUT_SECONDS", "20"))
    )
    db_enabled: bool = field(default_factory=lambda: _bool_env("DB_WRITE_ENABLED", False))
    oracle_user: Optional[str] = field(default_factory=lambda: os.getenv("ORACLE_USER") or None)
    oracle_password: Optional[str] = field(default_factory=lambda: os.getenv("ORACLE_PASSWORD") or None)
    oracle_dsn: Optional[str] = field(default_factory=lambda: os.getenv("ORACLE_DSN") or None)


def get_settings() -> OrchestratorSettings:
    return OrchestratorSettings()
