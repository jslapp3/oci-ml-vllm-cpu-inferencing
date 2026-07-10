from fastapi.testclient import TestClient

from orchestrator_api.app.config import OrchestratorSettings
from orchestrator_api.app.main import create_app


class FakeMLClient:
    settings = OrchestratorSettings(ml_service_base_url="http://ml-service")

    async def predict(self, payload):
        assert payload["series_id"] == "demo-series"
        assert "notes" not in payload
        return {
            "prediction_id": "prediction-1",
            "series_id": payload["series_id"],
            "model_name": "amazon/chronos-t5-small",
            "model_source": "https://huggingface.co/amazon/chronos-t5-small",
            "engine": "fallback",
            "loaded_public_model": False,
            "inference_timestamp": "2026-07-09T00:00:00+00:00",
            "prediction_length": payload["prediction_length"],
            "horizon": [],
            "summary": {
                "baseline": 100,
                "final_median": 112,
                "percent_change": 0.12,
                "trend_direction": "up",
                "volatility": 2.0,
                "uncertainty_ratio": 0.1,
                "risk_score": 0.25,
                "risk_band": "moderate",
                "confidence": 0.9,
            },
            "drivers": [],
            "warnings": [],
        }


class FakeLLMClient:
    async def extract_structured_features(self, notes):
        return {
            "available": True,
            "used_fallback": False,
            "model": "fake-llm",
            "features": {"signals": ["promo"]},
            "error": None,
        }

    async def generate_explanation(self, ml_output, notes=None):
        return {
            "available": True,
            "used_fallback": False,
            "model": "fake-llm",
            "text": "Demand is trending up with moderate risk.",
            "error": None,
        }

    async def generate_recommendations(self, ml_output, notes=None):
        return {
            "available": True,
            "used_fallback": False,
            "model": "fake-llm",
            "text": "- Check inventory.",
            "error": None,
        }


class FakeDBWriter:
    enabled = False

    async def write_inference_run(self, run_id, request_payload, response_payload):
        assert request_payload["series_id"] == "demo-series"
        assert response_payload["status"] == "completed"
        return {"enabled": False, "wrote": False, "error": None}


def test_orchestrator_combines_ml_llm_and_db_results():
    app = create_app(
        ml_client=FakeMLClient(),
        llm_client=FakeLLMClient(),
        db_writer=FakeDBWriter(),
    )
    client = TestClient(app)

    response = client.post(
        "/predict",
        json={
            "series_id": "demo-series",
            "values": [100, 102, 108],
            "prediction_length": 2,
            "notes": "Promotion starts tomorrow.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["ml_output"]["model_name"] == "amazon/chronos-t5-small"
    assert body["explanation"]["text"].startswith("Demand")
    assert body["recommendations"]["text"] == "- Check inventory."
    assert body["presentation"]["predictions_text"].startswith("Predictions")
    assert body["presentation"]["explanation_paragraph"] == "Demand is trending up with moderate risk."
    assert body["database_write"]["wrote"] is False
    assert body["warnings"] == []
