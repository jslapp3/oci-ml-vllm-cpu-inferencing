"""Schemas for the public orchestration API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator


class PredictionRequest(BaseModel):
    series_id: str = Field(default="default", min_length=1)
    values: List[float] = Field(..., min_length=2)
    timestamps: Optional[List[str]] = None
    prediction_length: int = Field(default=12, ge=1)
    quantile_levels: List[float] = Field(default_factory=lambda: [0.1, 0.5, 0.9])
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("values")
    def values_must_be_finite(cls, series_values: List[float]) -> List[float]:
        for value in series_values:
            if value != value or value in {float("inf"), float("-inf")}:
                raise ValueError("values must be finite numbers")
        return series_values

    @root_validator(skip_on_failure=True)
    def timestamps_match_values(cls, model_values: Dict[str, Any]) -> Dict[str, Any]:
        timestamps = model_values.get("timestamps")
        series_values = model_values.get("values")
        if timestamps is not None and series_values is not None:
            if len(timestamps) != len(series_values):
                raise ValueError("timestamps length must match values length")
        return model_values


class CombinedPredictionResponse(BaseModel):
    run_id: str
    status: str
    ml_output: Dict[str, Any]
    explanation: Dict[str, Any]
    recommendations: Dict[str, Any]
    extracted_features: Dict[str, Any]
    database_write: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
