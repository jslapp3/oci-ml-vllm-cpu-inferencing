"""Client for a vLLM OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from .config import LLMSettings, get_settings


class VLLMCompanionClient:
    def __init__(
        self,
        settings: Optional[LLMSettings] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.settings = settings or get_settings()
        self._http_client = http_client

    async def generate_explanation(self, ml_output: Dict[str, Any], notes: Optional[str] = None) -> Dict[str, Any]:
        prompt = (
            "Explain this time-series forecast for an operations stakeholder. "
            "Be concise, mention the risk band, trend direction, uncertainty, and the most important drivers. "
            "Do not invent data beyond the provided JSON.\n\n"
            f"Forecast JSON:\n{_compact_json(ml_output)}\n\n"
            f"Optional notes:\n{notes or 'None'}"
        )
        result = await self._chat(prompt, max_tokens=self.settings.max_tokens)
        if result["available"]:
            return result
        result["text"] = _fallback_explanation(ml_output)
        result["used_fallback"] = True
        return result

    async def generate_recommendations(self, ml_output: Dict[str, Any], notes: Optional[str] = None) -> Dict[str, Any]:
        prompt = (
            "Given this forecast output, produce 3 practical next actions. "
            "Keep each action short and tied to the forecast risk, uncertainty, or drivers. "
            "Return plain text bullets only.\n\n"
            f"Forecast JSON:\n{_compact_json(ml_output)}\n\n"
            f"Optional notes:\n{notes or 'None'}"
        )
        result = await self._chat(prompt, max_tokens=350)
        if result["available"]:
            return result
        result["text"] = _fallback_recommendations(ml_output)
        result["used_fallback"] = True
        return result

    async def extract_structured_features(self, notes: Optional[str]) -> Dict[str, Any]:
        if not notes:
            return {
                "available": False,
                "used_fallback": False,
                "model": self.settings.model_name,
                "features": {},
                "error": None,
            }

        prompt = (
            "Extract structured forecast context from the notes as compact JSON with keys "
            "signals, constraints, events, and urgency. Return JSON only.\n\n"
            f"Notes:\n{notes}"
        )
        result = await self._chat(prompt, max_tokens=300)
        if not result["available"]:
            return {
                "available": False,
                "used_fallback": True,
                "model": self.settings.model_name,
                "features": {"raw_notes": notes},
                "error": result["error"],
            }

        try:
            features = json.loads(result["text"])
        except json.JSONDecodeError:
            features = {"raw_llm_text": result["text"]}
        return {
            "available": True,
            "used_fallback": False,
            "model": self.settings.model_name,
            "features": features,
            "error": None,
        }

    async def _chat(self, user_prompt: str, max_tokens: int) -> Dict[str, Any]:
        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise ML forecasting companion. Ground responses in the supplied model output.",
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": max_tokens,
        }

        try:
            if self._http_client is not None:
                response = await self._http_client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"].strip()
            return {
                "available": True,
                "used_fallback": False,
                "model": self.settings.model_name,
                "text": text,
                "error": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "used_fallback": False,
                "model": self.settings.model_name,
                "text": "",
                "error": f"{type(exc).__name__}: {exc}",
            }


def _compact_json(payload: Dict[str, Any]) -> str:
    text = json.dumps(payload, default=str, separators=(",", ":"))
    return text[:8000]


def _fallback_explanation(ml_output: Dict[str, Any]) -> str:
    summary = ml_output.get("summary", {})
    return (
        "Forecast explanation generated from template because the vLLM endpoint is unavailable. "
        f"The forecast trend is {summary.get('trend_direction', 'unknown')} with "
        f"{summary.get('risk_band', 'unknown')} risk and confidence "
        f"{summary.get('confidence', 'unknown')}."
    )


def _fallback_recommendations(ml_output: Dict[str, Any]) -> str:
    summary = ml_output.get("summary", {})
    risk_band = summary.get("risk_band", "unknown")
    return (
        f"- Review the forecast because the current risk band is {risk_band}.\n"
        "- Check recent trend and volatility drivers before acting on the forecast.\n"
        "- Re-run inference after new observations arrive or after known events are resolved."
    )

