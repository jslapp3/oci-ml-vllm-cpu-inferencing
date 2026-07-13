import pytest
from pydantic import ValidationError

from ml_service.app.schemas import ForecastRequest
from orchestrator_api.app.schemas import PredictionRequest


@pytest.mark.parametrize("schema", [ForecastRequest, PredictionRequest])
def test_numeric_and_categorical_covariates_are_accepted(schema):
    request = schema(
        values=[10, 11, 12],
        prediction_length=2,
        past_covariates={
            "price": [1, 1.5, 2],
            "region": ["north", "north", "south"],
            "holiday": [False, False, True],
        },
        future_covariates={
            "price": [2.5, 3],
            "region": ["south", "south"],
            "holiday": [False, True],
        },
        future_timestamps=["2026-07-04", "2026-07-05"],
    )

    assert request.past_covariates["price"] == [1, 1.5, 2]
    assert request.future_covariates["region"] == ["south", "south"]


@pytest.mark.parametrize("schema", [ForecastRequest, PredictionRequest])
@pytest.mark.parametrize(
    "fields, message",
    [
        ({"past_covariates": {"promo": [0, 1]}}, "length must match values"),
        (
            {"past_covariates": {"promo": [0, 1, 0]}, "future_covariates": {"promo": [1]}},
            "length must match prediction_length",
        ),
        ({"future_timestamps": ["2026-07-04"]}, "length must match prediction_length"),
        ({"future_covariates": {"promo": [1, 1]}}, "must also have historical values"),
        ({"past_covariates": {"promo": [0, "yes", 1]}}, "mixed scalar types"),
        (
            {
                "past_covariates": {"promo": [0, 1, 0]},
                "future_covariates": {"promo": ["yes", "no"]},
            },
            "mixed scalar types",
        ),
        ({"past_covariates": {"promo": [0, float("inf"), 1]}}, "finite numbers"),
    ],
)
def test_invalid_covariates_are_rejected(schema, fields, message):
    with pytest.raises(ValidationError, match=message):
        schema(values=[10, 11, 12], prediction_length=2, **fields)
