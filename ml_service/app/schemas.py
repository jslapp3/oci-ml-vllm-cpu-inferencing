"""Pydantic schemas for forecasting requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator


class ForecastRequest(BaseModel):
    series_id: str = Field(default="default", min_length=1)
    values: List[float] = Field(..., min_length=2)
    timestamps: Optional[List[str]] = None
    prediction_length: int = Field(default=12, ge=1)
    quantile_levels: List[float] = Field(default_factory=lambda: [0.1, 0.5, 0.9])
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
    def timestamps_match_values(cls, model_values: Dict[str, Any]) -> Dict[str, Any]:
        timestamps = model_values.get("timestamps")
        series_values = model_values.get("values")
        if timestamps is not None and series_values is not None:
            if len(timestamps) != len(series_values):
                raise ValueError("timestamps length must match values length")
        return model_values


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


class ForecastResponse(BaseModel):
    prediction_id: str
    series_id: str
    model_name: str
    model_source: str
    model_version: Optional[str] = None
    engine: str
    loaded_public_model: bool
    inference_timestamp: str
    prediction_length: int
    horizon: List[ForecastPoint]
    summary: ForecastSummary
    drivers: List[DriverContribution]
    warnings: List[str] = Field(default_factory=list)
