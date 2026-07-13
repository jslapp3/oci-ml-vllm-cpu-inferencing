import csv
import io

from fastapi.testclient import TestClient

from orchestrator_api.app.config import OrchestratorSettings
from orchestrator_api.app.main import create_app


class RecordingMLClient:
    settings = OrchestratorSettings(ml_service_base_url="http://ml-service")

    def __init__(self):
        self.last_payload = None

    async def predict(self, payload):
        self.last_payload = payload
        horizon_timestamps = payload.get("future_timestamps") or ["2026-07-04"] * payload["prediction_length"]
        return {
            "prediction_id": "prediction-csv",
            "series_id": payload["series_id"],
            "model_name": "amazon/chronos-t5-small",
            "model_source": "https://huggingface.co/amazon/chronos-t5-small",
            "engine": "chronos",
            "model_family": "chronos",
            "covariates_used": {"past": [], "future": []},
            "loaded_public_model": True,
            "inference_timestamp": "2026-07-09T00:00:00+00:00",
            "prediction_length": payload["prediction_length"],
            "horizon": [
                {
                    "step": index + 1,
                    "timestamp": timestamp,
                    "median": 140.0 + index,
                    "lower": 130.0 + index,
                    "upper": 150.0 + index,
                    "quantiles": {
                        "q10": 130.0 + index,
                        "q50": 140.0 + index,
                        "q90": 150.0 + index,
                    },
                }
                for index, timestamp in enumerate(horizon_timestamps)
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
    assert ml_client.last_payload["past_covariates"] == {
        "promo_flag": [0.0, 0.0, 1.0],
        "inventory": [450.0, 430.0, 410.0],
    }
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


def test_predict_csv_trailing_future_rows_propagate_covariates_and_enriched_values():
    ml_client = RecordingMLClient()
    llm_client = RecordingLLMClient()
    app = create_app(
        ml_client=ml_client,
        llm_client=llm_client,
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)
    csv_text = (
        "date,demand,promo,inventory,region,weather\n"
        "2026-07-01,120,0,450,north,sunny\n"
        "2026-07-02,127,0,430,north,\n"
        "2026-07-03,131,1,410,north,cloudy\n"
        "2026-07-04,,1,400,north,rainy\n"
        "2026-07-05,,0,,south,sunny\n"
    )

    response = client.post(
        "/predict/csv",
        data={
            "date_column": "date",
            "target_column": "demand",
            "prediction_length": "2",
        },
        files={"file": ("future.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 200
    payload = ml_client.last_payload
    assert payload["future_timestamps"] == ["2026-07-04", "2026-07-05"]
    assert payload["past_covariates"] == {
        "promo": [0.0, 0.0, 1.0],
        "inventory": [450.0, 430.0, 410.0],
        "region": ["north", "north", "north"],
    }
    assert payload["future_covariates"] == {
        "promo": [1.0, 0.0],
        "region": ["north", "south"],
    }
    assert payload["metadata"]["excluded_covariate_columns"] == ["weather"]

    warnings = response.json()["warnings"]
    assert any("Interpreted 2 trailing" in warning for warning in warnings)
    assert any("inventory" in warning and "past-only" in warning for warning in warnings)
    assert any("Excluded covariate 'weather'" in warning for warning in warnings)
    assert "Future covariate summary" in llm_client.last_notes
    assert "rainy" in llm_client.last_notes

    enriched = response.json()["presentation"]["enriched_csv"]
    rows = list(csv.DictReader(io.StringIO(enriched)))
    future_rows = [row for row in rows if row["row_type"] == "forecast"]
    assert future_rows[0]["timestamp"] == "2026-07-04"
    assert future_rows[0]["inventory"] == "400"
    assert future_rows[0]["weather"] == "rainy"
    assert future_rows[1]["timestamp"] == "2026-07-05"
    assert future_rows[1]["region"] == "south"
    assert future_rows[1]["weather"] == "sunny"


def test_predict_csv_rejects_future_row_count_that_does_not_match_horizon():
    app = create_app(
        ml_client=RecordingMLClient(),
        llm_client=RecordingLLMClient(),
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)
    csv_text = "date,demand,promo\n2026-07-01,10,0\n2026-07-02,11,0\n2026-07-03,,1\n"

    response = client.post(
        "/predict/csv",
        data={"date_column": "date", "target_column": "demand", "prediction_length": "2"},
        files={"file": ("bad-future.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 400
    assert "must equal prediction_length" in response.json()["detail"]


def test_predict_csv_keeps_existing_internal_blank_target_behavior():
    ml_client = RecordingMLClient()
    app = create_app(
        ml_client=ml_client,
        llm_client=RecordingLLMClient(),
        db_writer=NoopDBWriter(),
    )
    client = TestClient(app)
    csv_text = (
        "date,demand,promo\n"
        "2026-07-01,10,0\n"
        "2026-07-02,,1\n"
        "2026-07-03,12,0\n"
    )

    response = client.post(
        "/predict/csv",
        data={"date_column": "date", "target_column": "demand", "prediction_length": "1"},
        files={"file": ("internal-blank.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 200
    assert ml_client.last_payload["values"] == [10.0, 12.0]
    assert ml_client.last_payload["past_covariates"] == {"promo": [0.0, 0.0]}
    assert any("Skipped 1 row" in warning for warning in response.json()["warnings"])
