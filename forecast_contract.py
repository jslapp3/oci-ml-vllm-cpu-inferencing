"""Shared validation helpers for the public and ML forecast contracts."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Union

from pydantic import StrictBool, StrictFloat, StrictInt, StrictStr


CovariateScalar = Union[StrictBool, StrictInt, StrictFloat, StrictStr]
CovariateMap = Dict[str, List[CovariateScalar]]


def validate_forecast_contract(model_values: Dict[str, Any]) -> Dict[str, Any]:
    """Validate aligned timestamps and optional Chronos-2 covariates."""

    timestamps = model_values.get("timestamps")
    series_values = model_values.get("values")
    prediction_length = model_values.get("prediction_length")
    past_covariates: Optional[CovariateMap] = model_values.get("past_covariates")
    future_covariates: Optional[CovariateMap] = model_values.get("future_covariates")
    future_timestamps = model_values.get("future_timestamps")

    if timestamps is not None and series_values is not None and len(timestamps) != len(series_values):
        raise ValueError("timestamps length must match values length")

    if future_timestamps is not None and prediction_length is not None:
        if len(future_timestamps) != prediction_length:
            raise ValueError("future_timestamps length must match prediction_length")

    for name, values in (past_covariates or {}).items():
        _validate_covariate_name(name)
        _validate_covariate_values(name, values)
        if series_values is not None and len(values) != len(series_values):
            raise ValueError(f"past_covariates['{name}'] length must match values length")

    for name, values in (future_covariates or {}).items():
        _validate_covariate_name(name)
        _validate_covariate_values(name, values)
        if prediction_length is not None and len(values) != prediction_length:
            raise ValueError(f"future_covariates['{name}'] length must match prediction_length")
        if not past_covariates or name not in past_covariates:
            raise ValueError(f"future covariate '{name}' must also have historical values")
        _validate_covariate_values(name, [*past_covariates[name], *values])

    return model_values


def _validate_covariate_name(name: str) -> None:
    if not name.strip():
        raise ValueError("covariate names must not be blank")


def _validate_covariate_values(name: str, values: List[CovariateScalar]) -> None:
    kinds = set()
    for value in values:
        if isinstance(value, bool):
            kinds.add("boolean")
        elif isinstance(value, (int, float)):
            try:
                finite = math.isfinite(value)
            except (OverflowError, TypeError):
                finite = False
            if not finite:
                raise ValueError(f"covariate '{name}' must contain only finite numbers, strings, or booleans")
            kinds.add("number")
        elif isinstance(value, str):
            kinds.add("string")
        else:  # pragma: no cover - strict Pydantic scalar types reject this first
            raise ValueError(f"covariate '{name}' must contain only finite numbers, strings, or booleans")

    if len(kinds) > 1:
        raise ValueError(
            f"covariate '{name}' contains mixed scalar types; only integer/float mixtures are compatible"
        )
