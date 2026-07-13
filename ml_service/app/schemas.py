"""Pydantic schemas for forecasting requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator

from forecast_contract import CovariateMap, validate_forecast_contract


class ForecastRequest(BaseModel):
    series_id: str = Field(default="default", min_length=1)
    values: List[float] = Field(..., min_length=2)
    timestamps: Optional[List[str]] = None
    prediction_length: int = Field(default=12, ge=1)
    quantile_levels: List[float] = Field(default_factory=lambda: [0.1, 0.5, 0.9])
    past_covariates: Optional[CovariateMap] = None
    future_covariates: Optional[CovariateMap] = None
    future_timestamps: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("values")
    def values_must_be_finite(cls, series_values: List[float]) -> List[float]:
        for value in series_values:
            if value != value or value in {float("inf"), float("-inf")}:
                raise ValueError("values must be finite numbers")
        return series_values

    @validator("quantile_levels")
    def quantiles_must_be_probabilities(cls, levels: List[float]) -> List[float]:
        if not levels:
            raise ValueError("at least one quantile level is required")
        for value in levels:
            if value <= 0 or value >= 1:
                raise ValueError("quantile levels must be between 0 and 1")
        return levels

    @root_validator(skip_on_failure=True)
    def aligned_forecast_inputs(cls, model_values: Dict[str, Any]) -> Dict[str, Any]:
        return validate_forecast_contract(model_values)


class ForecastPoint(BaseModel):
    step: int
    timestamp: Optional[str] = None
    median: float
    lower: float
    upper: float
    quantiles: Dict[str, float]


class DriverContribution(BaseModel):
    name: str
    contribution: float
    direction: str
    description: str


class ForecastSummary(BaseModel):
    baseline: float
    final_median: float
    percent_change: float
    trend_direction: str
    volatility: float
    uncertainty_ratio: float
    risk_score: float
    risk_band: str
    confidence: float


class CovariatesUsed(BaseModel):
    past: List[str] = Field(default_factory=list)
    future: List[str] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    prediction_id: str
    series_id: str
    model_name: str
    model_source: str
    model_version: Optional[str] = None
    engine: str
    model_family: str
    covariates_used: CovariatesUsed = Field(default_factory=CovariatesUsed)
    loaded_public_model: bool
    inference_timestamp: str
    prediction_length: int
    horizon: List[ForecastPoint]
    summary: ForecastSummary
    drivers: List[DriverContribution]
    warnings: List[str] = Field(default_factory=list)
