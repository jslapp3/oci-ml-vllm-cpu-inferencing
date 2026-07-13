import pytest

from ml_service.app.config import MLSettings
from ml_service.app.forecasting import ForecastingService
from ml_service.app.schemas import ForecastRequest


def test_force_fallback_records_model_loading_reason():
    service = ForecastingService(MLSettings(force_fallback=True))
    response = service.predict(
        ForecastRequest(
            series_id="fallback-series",
            values=[20, 18, 17, 16],
            prediction_length=3,
        )
    )

    assert response.engine == "fallback"
    assert response.model_family == "fallback"
    assert response.loaded_public_model is False
    assert "ML_FORCE_FALLBACK" in response.warnings[0]
    assert service.health()["load_error"] == "ML_FORCE_FALLBACK is enabled"


def test_fallback_explicitly_ignores_covariates():
    service = ForecastingService(MLSettings(force_fallback=True))
    response = service.predict(
        ForecastRequest(
            values=[20, 18, 17],
            prediction_length=2,
            past_covariates={"promotion": [0, 0, 1]},
            future_covariates={"promotion": [1, 1]},
        )
    )

    assert response.engine == "fallback"
    assert response.model_family == "fallback"
    assert response.covariates_used.past == []
    assert response.covariates_used.future == []
    assert any("deterministic fallback" in warning for warning in response.warnings)


def test_prediction_length_limit_is_enforced():
    service = ForecastingService(
        MLSettings(
            load_public_model=False,
            max_prediction_length=2,
        )
    )

    with pytest.raises(ValueError):
        service.predict(
            ForecastRequest(
                series_id="too-long",
                values=[1, 2, 3],
                prediction_length=3,
            )
        )


def test_normalized_output_mapping_has_expected_bounds():
    service = ForecastingService(MLSettings(load_public_model=False))
    response = service.predict(
        ForecastRequest(
            series_id="normalization",
            values=[50, 51, 52, 60, 64, 70],
            prediction_length=5,
        )
    )

    assert -10 < response.summary.percent_change < 10
    assert 0 <= response.summary.uncertainty_ratio
    assert 0 <= response.summary.risk_score <= 1
    assert response.summary.risk_band in {"low", "moderate", "elevated", "high"}
    assert {driver.name for driver in response.drivers} == {
        "recent_trend",
        "recent_volatility",
        "latest_level_shift",
    }
