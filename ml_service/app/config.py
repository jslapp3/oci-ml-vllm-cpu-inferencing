"""Configuration for the Chronos forecasting service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


DEFAULT_CHRONOS_MODEL_NAME = "autogluon/chronos-2-small"
DEFAULT_CHRONOS_MODEL_REVISION = "ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a"
DEFAULT_CHRONOS_MODEL_SOURCE_URL = "https://huggingface.co/autogluon/chronos-2-small"


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return value or None


@dataclass(frozen=True)
class MLSettings:
    app_name: str = field(default_factory=lambda: os.getenv("ML_SERVICE_NAME", "chronos-forecast-ml-service"))
    model_name: str = field(default_factory=lambda: os.getenv("CHRONOS_MODEL_NAME", DEFAULT_CHRONOS_MODEL_NAME))
    model_revision: Optional[str] = field(default_factory=lambda: _optional_env("CHRONOS_MODEL_REVISION"))
    model_source_url: str = field(default_factory=lambda: os.getenv("CHRONOS_MODEL_SOURCE_URL", ""))
    device: str = field(default_factory=lambda: os.getenv("CHRONOS_DEVICE", "cpu"))
    chronos_num_samples: int = field(default_factory=lambda: int(os.getenv("CHRONOS_NUM_SAMPLES", "100")))
    max_prediction_length: int = field(default_factory=lambda: int(os.getenv("MAX_PREDICTION_LENGTH", "96")))
    load_public_model: bool = field(default_factory=lambda: _bool_env("ML_LOAD_PUBLIC_MODEL", True))
    force_fallback: bool = field(default_factory=lambda: _bool_env("ML_FORCE_FALLBACK", False))
    preload_model: bool = field(default_factory=lambda: _bool_env("ML_PRELOAD_MODEL", True))
    hf_home: str = field(default_factory=lambda: os.getenv("HF_HOME", os.path.abspath("hf_cache")))

    def __post_init__(self) -> None:
        revision_was_not_configured = "CHRONOS_MODEL_REVISION" not in os.environ
        if (
            self.model_name == DEFAULT_CHRONOS_MODEL_NAME
            and self.model_revision is None
            and revision_was_not_configured
        ):
            object.__setattr__(self, "model_revision", DEFAULT_CHRONOS_MODEL_REVISION)

        if not self.model_source_url:
            source_url = (
                DEFAULT_CHRONOS_MODEL_SOURCE_URL
                if self.model_name == DEFAULT_CHRONOS_MODEL_NAME
                else f"https://huggingface.co/{self.model_name}"
            )
            object.__setattr__(self, "model_source_url", source_url)


def get_settings() -> MLSettings:
    return MLSettings()
