import asyncio

import httpx

from llm_service.app.client import VLLMCompanionClient
from llm_service.app.config import LLMSettings


class FailingAsyncClient:
    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")


class FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class SuccessfulAsyncClient:
    async def post(self, *args, **kwargs):
        return FakeResponse('{"signals":["promo"],"constraints":["inventory"],"events":[],"urgency":"medium"}')


class ThinkingAsyncClient:
    async def post(self, *args, **kwargs):
        return FakeResponse("<think>private reasoning that should not be returned</think>\nFinal forecast explanation.")


def test_vllm_client_explanation_falls_back_when_endpoint_unavailable():
    client = VLLMCompanionClient(
        LLMSettings(base_url="http://vllm.example/v1", model_name="test-model"),
        http_client=FailingAsyncClient(),
    )
    result = asyncio.run(
        client.generate_explanation(
            {
                "summary": {
                    "trend_direction": "up",
                    "risk_band": "moderate",
                    "confidence": 0.8,
                }
            }
        )
    )

    assert result["available"] is False
    assert result["used_fallback"] is True
    assert "template" in result["text"]
    assert "ConnectError" in result["error"]


def test_vllm_client_extracts_structured_features_from_json_response():
    client = VLLMCompanionClient(
        LLMSettings(base_url="http://vllm.example/v1", model_name="test-model"),
        http_client=SuccessfulAsyncClient(),
    )
    result = asyncio.run(client.extract_structured_features("Promotion and inventory constraint."))

    assert result["available"] is True
    assert result["used_fallback"] is False
    assert result["features"]["signals"] == ["promo"]
    assert result["features"]["constraints"] == ["inventory"]


def test_vllm_client_strips_reasoning_markup_from_model_text():
    client = VLLMCompanionClient(
        LLMSettings(base_url="http://vllm.example/v1", model_name="test-model"),
        http_client=ThinkingAsyncClient(),
    )
    result = asyncio.run(client.generate_explanation({"summary": {"trend_direction": "flat"}}))

    assert result["available"] is True
    assert result["text"] == "Final forecast explanation."
    assert "<think>" not in result["text"]
    assert "private reasoning" not in result["text"]
