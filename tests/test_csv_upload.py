from fastapi.testclient import TestClient

from orchestrator_api.app.config import OrchestratorSettings
from orchestrator_api.app.main import create_app


class RecordingMLClient:
    settings = OrchestratorSettings(ml_service_base_url="http://ml-service")

    def __init__(self):
        self.last_payload = None

    async def predict(self, payload):
        self.last_payload = payload
        return {
            "prediction_id": "prediction-csv",
            "series_id": payload["series_id"],
            "model_name": "amazon/chronos-t5-small",
            "model_source": "https://huggingface.co/amazon/chronos-t5-small",
            "engine": "chronos",
            "loaded_public_model": True,
            "inference_timestamp": "2026-07-09T00:00:00+00:00",
            "prediction_length": payload["prediction_length"],
            "horizon": [
                {
                    "step": 1,
                    "timestamp": "2026-07-04",
                    "median": 140.0,
                    "lower": 130.0,
                    "upper": 150.0,
                    "quantiles": {"q10": 130.0, "q50": 140.0, "q90": 150.0},
                }
            ],
            "summary": {
                "baseline": 126,
                "final_median": 140,
                "percent_change": 0.11,
                "trend_direction": "up",
                "volatility": 4.5,
                "uncertainty_ratio": 0.14,
                "risk_score": 0.28,
                "risk_band": "moderate",
                "confidence": 0.86,
            },
            "drivers": [],
            "warnings": [],
        }


class RecordingLLMClient:
    def __init__(self):
        self.last_notes = None

    async def extract_structured_features(self, notes):
        self.last_notes = notes
        return {
            "available": True,
            "used_fallback": False,
            "model": "fake-llm",
            "features": {"signals": ["promo"]},
            "error": None,
        }

    async def generate_explanation(self, ml_output, notes=None):
        self.last_notes = notes
        return {
            "available": True,
            "used_fallback": False,
            "model": "fake-llm",
            "text": "Promo lift and constrained inventory are consistent with an upward demand forecast.",
            "error": None,
        }

    async def generate_recommendations(self, ml_output, notes=None):
        return {
            "available": True,
            "used_fallback": False,
            "model": "fake-llm",
            "text": "- Check inventory before the promotion starts.",
            "error": None,
        }


class NoopDBWriter:
    enabled = False

    async def write_inference_run(self, run_id, request_payload, response_payload):
        return {"enabled": False, "wrote": False, "error": None}


def test_predict_csv_upload_returns_pretty_response_and_enriched_csv():
    ml_client = RecordingMLClient()
    llm_client = RecordingLLMClient()
    app = create_app(
        ml_client=ml_client,
        llm_client=llm_client,
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)
    csv_text = (
        "date,demand,promo_flag,inventory\n"
        "2026-07-02,127,0,430\n"
        "2026-07-01,120,0,450\n"
        "2026-07-03,131,1,410\n"
    )

    response = client.post(
        "/predict/csv",
        data={
            "series_id": "store-42-demand",
            "date_column": "date",
            "target_column": "demand",
            "prediction_length": "1",
            "notes": "Promotion starts next week.",
        },
        files={"file": ("demand.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert ml_client.last_payload["series_id"] == "store-42-demand"
    assert ml_client.last_payload["timestamps"] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert ml_client.last_payload["values"] == [120.0, 127.0, 131.0]
    assert ml_client.last_payload["metadata"]["covariate_columns"] == ["promo_flag", "inventory"]
    assert "Covariate summary" in llm_client.last_notes
    assert "inventory" in llm_client.last_notes

    presentation = body["presentation"]
    assert presentation["predictions_text"] == "Predictions\n\n* 2026-07-04: 140 (range 130 to 150)"
    assert presentation["explanation_paragraph"].startswith("Promo lift")
    assert "row_type,timestamp,actual_value" in presentation["enriched_csv"]
    assert "actual,2026-07-01,120" in presentation["enriched_csv"]
    assert "forecast,2026-07-04,,140,130,150" in presentation["enriched_csv"]
    assert "Promo lift and constrained inventory" in presentation["enriched_csv"]


def test_predict_csv_upload_can_return_markdown_report():
    app = create_app(
        ml_client=RecordingMLClient(),
        llm_client=RecordingLLMClient(),
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)
    csv_text = "date,demand\n2026-07-01,120\n2026-07-02,127\n2026-07-03,131\n"

    response = client.post(
        "/predict/csv",
        data={
            "series_id": "store-42-demand",
            "date_column": "date",
            "target_column": "demand",
            "prediction_length": "1",
            "response_format": "markdown",
        },
        files={"file": ("demand.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# Forecast Report" in response.text
    assert "* 2026-07-04: 140 (range 130 to 150)" in response.text
    assert "Explanation" in response.text
    assert "Promo lift" in response.text


def test_predict_csv_upload_can_return_enriched_csv_directly():
    app = create_app(
        ml_client=RecordingMLClient(),
        llm_client=RecordingLLMClient(),
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)
    csv_text = "date,demand\n2026-07-01,120\n2026-07-02,127\n2026-07-03,131\n"

    response = client.post(
        "/predict/csv",
        data={
            "series_id": "store-42-demand",
            "date_column": "date",
            "target_column": "demand",
            "prediction_length": "1",
            "response_format": "csv",
        },
        files={"file": ("demand.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="forecast_enriched.csv"'
    assert "row_type,timestamp,actual_value" in response.text
    assert "forecast,2026-07-04,,140,130,150" in response.text


def test_predict_csv_rejects_missing_target_column():
    app = create_app(
        ml_client=RecordingMLClient(),
        llm_client=RecordingLLMClient(),
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)

    response = client.post(
        "/predict/csv",
        data={"date_column": "date", "target_column": "demand"},
        files={"file": ("bad.csv", "date,value\n2026-07-01,10\n", "text/csv")},
    )

    assert response.status_code == 400
    assert "missing target column" in response.json()["detail"]
