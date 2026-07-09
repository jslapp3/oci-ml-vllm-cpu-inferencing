"""HTTP client for the ML forecasting service."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import OrchestratorSettings, get_settings


class MLServiceClient:
    def __init__(
        self,
        settings: Optional[OrchestratorSettings] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.settings = settings or get_settings()
        self._http_client = http_client

    async def predict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.settings.ml_service_base_url.rstrip('/')}/predict"
        if self._http_client is not None:
            response = await self._http_client.post(url, json=payload)
        else:
            async with httpx.AsyncClient(timeout=self.settings.ml_service_timeout_seconds) as client:
                response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

