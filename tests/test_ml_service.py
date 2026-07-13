from fastapi.testclient import TestClient

from ml_service.app.config import MLSettings
from ml_service.app.forecasting import ForecastingService
from ml_service.app.main import create_app
from ml_service.app.schemas import ForecastRequest


def test_forecast_response_shape_uses_fallback_when_public_model_disabled():
    service = ForecastingService(
        MLSettings(
            load_public_model=False,
            force_fallback=False,
            max_prediction_length=12,
        )
    )
    request = ForecastRequest(
        series_id="series-a",
        timestamps=["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
        values=[100.0, 105.0, 111.0, 118.0],
        prediction_length=4,
    )

    response = service.predict(request)

    assert response.series_id == "series-a"
    assert response.model_name == "autogluon/chronos-2-small"
    assert response.engine == "fallback"
    assert response.model_family == "fallback"
    assert response.covariates_used.past == []
    assert response.loaded_public_model is False
    assert len(response.horizon) == 4
    assert response.horizon[0].timestamp == "2026-07-05"
    assert "q50" in response.horizon[0].quantiles
    assert response.summary.risk_band in {"low", "moderate", "elevated", "high"}
    assert 0 <= response.summary.risk_score <= 1
    assert 0 < response.summary.confidence <= 0.99
    assert response.drivers
    assert response.warnings


def test_fastapi_predict_endpoint_returns_forecast():
    service = ForecastingService(MLSettings(load_public_model=False, max_prediction_length=12))
    app = create_app(service)
    client = TestClient(app)

    response = client.post(
        "/predict",
        json={
            "series_id": "series-b",
            "values": [10, 12, 13, 15],
            "prediction_length": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["series_id"] == "series-b"
    assert body["engine"] == "fallback"
    assert len(body["horizon"]) == 2
    assert body["summary"]["trend_direction"] in {"up", "down", "flat"}
