"""Configuration for the Chronos forecasting service."""

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
class MLSettings:
    app_name: str = field(default_factory=lambda: os.getenv("ML_SERVICE_NAME", "chronos-forecast-ml-service"))
    model_name: str = field(default_factory=lambda: os.getenv("CHRONOS_MODEL_NAME", "amazon/chronos-t5-small"))
    model_revision: Optional[str] = field(default_factory=lambda: os.getenv("CHRONOS_MODEL_REVISION") or None)
    model_source_url: str = field(
        default_factory=lambda: os.getenv(
            "CHRONOS_MODEL_SOURCE_URL",
            "https://huggingface.co/amazon/chronos-t5-small",
        )
    )
    device: str = field(default_factory=lambda: os.getenv("CHRONOS_DEVICE", "cpu"))
    chronos_num_samples: int = field(default_factory=lambda: int(os.getenv("CHRONOS_NUM_SAMPLES", "100")))
    max_prediction_length: int = field(default_factory=lambda: int(os.getenv("MAX_PREDICTION_LENGTH", "96")))
    load_public_model: bool = field(default_factory=lambda: _bool_env("ML_LOAD_PUBLIC_MODEL", True))
    force_fallback: bool = field(default_factory=lambda: _bool_env("ML_FORCE_FALLBACK", False))


def get_settings() -> MLSettings:
    return MLSettings()
