"""Configuration for the vLLM companion client."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMSettings:
    base_url: str = field(default_factory=lambda: os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"))
    model_name: str = field(default_factory=lambda: os.getenv("VLLM_MODEL", "Qwen/Qwen3-0.6B"))
    api_key: str = field(default_factory=lambda: os.getenv("VLLM_API_KEY", "EMPTY"))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("VLLM_TIMEOUT_SECONDS", "10")))
    temperature: float = field(default_factory=lambda: float(os.getenv("VLLM_TEMPERATURE", "0.2")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("VLLM_MAX_TOKENS", "500")))


def get_settings() -> LLMSettings:
    return LLMSettings()
