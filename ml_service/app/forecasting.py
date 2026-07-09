"""Forecasting implementation for Chronos with a deterministic fallback."""

from __future__ import annotations

import math
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from .config import MLSettings, get_settings
from .schemas import (
    DriverContribution,
    ForecastPoint,
    ForecastRequest,
    ForecastResponse,
    ForecastSummary,
)


class ForecastingService:
    """Lazy-loads Chronos and falls back to a deterministic trend model."""

    def __init__(self, settings: Optional[MLSettings] = None):
        self.settings = settings or get_settings()
        self._pipeline = None
        self._load_attempted = False
        self._load_error: Optional[str] = None

    @property
    def loaded_public_model(self) -> bool:
        return self._pipeline is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def health(self) -> dict:
        return {
            "status": "ok",
            "model_name": self.settings.model_name,
            "model_source": self.settings.model_source_url,
            "load_public_model": self.settings.load_public_model,
            "force_fallback": self.settings.force_fallback,
            "model_load_attempted": self._load_attempted,
            "loaded_public_model": self.loaded_public_model,
            "load_error": self._load_error,
        }

    def predict(self, request: ForecastRequest) -> ForecastResponse:
        if request.prediction_length > self.settings.max_prediction_length:
            raise ValueError(
                f"prediction_length exceeds MAX_PREDICTION_LENGTH={self.settings.max_prediction_length}"
            )

        quantile_levels = _normalize_quantile_levels(request.quantile_levels)
        warnings: List[str] = []
        inference_time = datetime.now(timezone.utc)
        engine = "chronos"

        pipeline = self._load_pipeline()
        if pipeline is not None:
            try:
                horizon = self._predict_with_chronos(request, quantile_levels)
            except Exception as exc:  # pragma: no cover - exercised only with Chronos installed
                warnings.append(f"Chronos inference failed; used fallback. Cause: {type(exc).__name__}: {exc}")
                horizon = self._fallback_forecast(request, quantile_levels)
                engine = "fallback"
        else:
            if self._load_error:
                warnings.append(f"Chronos model unavailable; used fallback. Cause: {self._load_error}")
            horizon = self._fallback_forecast(request, quantile_levels)
            engine = "fallback"

        summary = _summarize_forecast(request.values, horizon)
        drivers = _build_driver_contributions(request.values, summary)
        return ForecastResponse(
            prediction_id=str(uuid.uuid4()),
            series_id=request.series_id,
            model_name=self.settings.model_name,
            model_source=self.settings.model_source_url,
            model_version=self.settings.model_revision,
            engine=engine,
            loaded_public_model=self.loaded_public_model,
            inference_timestamp=inference_time.isoformat(),
            prediction_length=request.prediction_length,
            horizon=horizon,
            summary=summary,
            drivers=drivers,
            warnings=warnings,
        )

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        if self.settings.force_fallback:
            self._load_error = "ML_FORCE_FALLBACK is enabled"
            return None
        if not self.settings.load_public_model:
            self._load_error = "ML_LOAD_PUBLIC_MODEL is disabled"
            return None
        if self._load_attempted:
            return None

        self._load_attempted = True
        try:
            import torch

            try:
                from chronos import ChronosPipeline as PipelineClass
            except ImportError:  # pragma: no cover - depends on installed chronos version
                from chronos import BaseChronosPipeline as PipelineClass

            kwargs = {
                "device_map": self.settings.device,
                "torch_dtype": torch.float32,
            }
            if self.settings.model_revision:
                kwargs["revision"] = self.settings.model_revision
            self._pipeline = PipelineClass.from_pretrained(self.settings.model_name, **kwargs)
            self._load_error = None
            return self._pipeline
        except Exception as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"
            self._pipeline = None
            return None

    def _predict_with_chronos(
        self,
        request: ForecastRequest,
        quantile_levels: Sequence[float],
    ) -> List[ForecastPoint]:
        import numpy as np
        import torch

        context = torch.tensor(request.values, dtype=torch.float32)
        forecast = self._pipeline.predict(
            context,
            request.prediction_length,
            num_samples=self.settings.chronos_num_samples,
        )
        if hasattr(forecast, "detach"):
            forecast_array = forecast.detach().cpu().numpy()
        else:
            forecast_array = np.asarray(forecast)

        forecast_array = np.asarray(forecast_array)
        if forecast_array.ndim == 3:
            forecast_array = forecast_array[0]
        if forecast_array.ndim == 1:
            forecast_array = forecast_array.reshape(1, -1)
        if forecast_array.shape[-1] != request.prediction_length and forecast_array.shape[0] == request.prediction_length:
            forecast_array = forecast_array.transpose()

        quantile_values = np.quantile(forecast_array, quantile_levels, axis=0)
        return _points_from_quantiles(
            quantile_levels=quantile_levels,
            quantile_values=quantile_values.tolist(),
            timestamps=_future_timestamps(request.timestamps, request.prediction_length),
        )

    def _fallback_forecast(
        self,
        request: ForecastRequest,
        quantile_levels: Sequence[float],
    ) -> List[ForecastPoint]:
        values = request.values
        last_value = values[-1]
        deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
        recent_deltas = deltas[-min(6, len(deltas)) :] if deltas else [0.0]
        slope = statistics.fmean(recent_deltas) if recent_deltas else 0.0
        volatility = _safe_std(recent_deltas)
        baseline_scale = max(abs(last_value), abs(statistics.fmean(values[-min(6, len(values)) :])), 1.0)
        base_spread = max(volatility, baseline_scale * 0.04)

        timestamps = _future_timestamps(request.timestamps, request.prediction_length)
        points: List[ForecastPoint] = []
        for step in range(1, request.prediction_length + 1):
            damped_slope = slope * (0.92 ** (step - 1))
            median = last_value + damped_slope * step
            spread = base_spread * math.sqrt(step) + abs(slope) * 0.15 * step
            quantiles = {
                _quantile_label(level): round(median + _approx_z(level) * spread, 6)
                for level in quantile_levels
            }
            median_value = quantiles.get("q50", round(median, 6))
            lower = min(value for key, value in quantiles.items() if key != "q50") if len(quantiles) > 1 else median_value
            upper = max(value for key, value in quantiles.items() if key != "q50") if len(quantiles) > 1 else median_value
            points.append(
                ForecastPoint(
                    step=step,
                    timestamp=timestamps[step - 1],
                    median=median_value,
                    lower=round(lower, 6),
                    upper=round(upper, 6),
                    quantiles=quantiles,
                )
            )
        return points


def _normalize_quantile_levels(levels: Iterable[float]) -> List[float]:
    normalized = sorted({round(float(level), 4) for level in levels if 0 < float(level) < 1})
    if 0.5 not in normalized:
        normalized.append(0.5)
        normalized.sort()
    return normalized


def _quantile_label(level: float) -> str:
    return f"q{int(round(level * 100)):02d}"


def _approx_z(level: float) -> float:
    lookup = {
        0.01: -2.326,
        0.05: -1.645,
        0.1: -1.282,
        0.25: -0.674,
        0.5: 0.0,
        0.75: 0.674,
        0.9: 1.282,
        0.95: 1.645,
        0.99: 2.326,
    }
    rounded = round(level, 2)
    if rounded in lookup:
        return lookup[rounded]
    return (level - 0.5) * 3.0


def _points_from_quantiles(
    quantile_levels: Sequence[float],
    quantile_values: Sequence[Sequence[float]],
    timestamps: Sequence[Optional[str]],
) -> List[ForecastPoint]:
    points: List[ForecastPoint] = []
    labels = [_quantile_label(level) for level in quantile_levels]
    for step in range(len(quantile_values[0])):
        quantiles = {
            label: round(float(quantile_values[index][step]), 6)
            for index, label in enumerate(labels)
        }
        median = quantiles["q50"]
        non_median_values = [value for label, value in quantiles.items() if label != "q50"]
        lower = min(non_median_values) if non_median_values else median
        upper = max(non_median_values) if non_median_values else median
        points.append(
            ForecastPoint(
                step=step + 1,
                timestamp=timestamps[step],
                median=median,
                lower=lower,
                upper=upper,
                quantiles=quantiles,
            )
        )
    return points


def _future_timestamps(timestamps: Optional[Sequence[str]], prediction_length: int) -> List[Optional[str]]:
    if not timestamps:
        return [None] * prediction_length
    try:
        last = _parse_timestamp(timestamps[-1])
        previous = _parse_timestamp(timestamps[-2]) if len(timestamps) > 1 else None
    except ValueError:
        return [None] * prediction_length

    delta = last - previous if previous is not None else timedelta(days=1)
    if delta.total_seconds() == 0:
        delta = timedelta(days=1)
    date_only = "T" not in timestamps[-1]
    future = []
    for step in range(1, prediction_length + 1):
        value = last + delta * step
        future.append(value.date().isoformat() if date_only else value.isoformat())
    return future


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _safe_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(statistics.pstdev(values))


def _summarize_forecast(values: Sequence[float], horizon: Sequence[ForecastPoint]) -> ForecastSummary:
    recent_values = values[-min(6, len(values)) :]
    baseline = float(statistics.fmean(recent_values))
    final_median = float(horizon[-1].median)
    denominator = max(abs(baseline), 1e-6)
    percent_change = (final_median - baseline) / denominator
    final_width = max(horizon[-1].upper - horizon[-1].lower, 0.0)
    uncertainty_ratio = final_width / max(abs(final_median), denominator, 1e-6)
    risk_score = min(1.0, abs(percent_change) * 1.4 + uncertainty_ratio * 0.45)

    if risk_score >= 0.7:
        risk_band = "high"
    elif risk_score >= 0.45:
        risk_band = "elevated"
    elif risk_score >= 0.2:
        risk_band = "moderate"
    else:
        risk_band = "low"

    if percent_change > 0.03:
        trend_direction = "up"
    elif percent_change < -0.03:
        trend_direction = "down"
    else:
        trend_direction = "flat"

    confidence = max(0.05, min(0.99, 1.0 - min(uncertainty_ratio, 0.95)))
    return ForecastSummary(
        baseline=round(baseline, 6),
        final_median=round(final_median, 6),
        percent_change=round(percent_change, 6),
        trend_direction=trend_direction,
        volatility=round(_safe_std(recent_values), 6),
        uncertainty_ratio=round(uncertainty_ratio, 6),
        risk_score=round(risk_score, 6),
        risk_band=risk_band,
        confidence=round(confidence, 6),
    )


def _build_driver_contributions(values: Sequence[float], summary: ForecastSummary) -> List[DriverContribution]:
    recent_values = list(values[-min(6, len(values)) :])
    deltas = [recent_values[index] - recent_values[index - 1] for index in range(1, len(recent_values))]
    trend = statistics.fmean(deltas) if deltas else 0.0
    level = max(abs(statistics.fmean(recent_values)), 1e-6)
    volatility_ratio = summary.volatility / level
    level_shift = (recent_values[-1] - statistics.fmean(recent_values)) / level

    return [
        DriverContribution(
            name="recent_trend",
            contribution=round(max(min(trend / level, 1.0), -1.0), 6),
            direction="up" if trend > 0 else "down" if trend < 0 else "flat",
            description="Average recent step-to-step movement in the input series.",
        ),
        DriverContribution(
            name="recent_volatility",
            contribution=round(min(volatility_ratio, 1.0), 6),
            direction="risk_increase" if volatility_ratio > 0.1 else "neutral",
            description="Recent variation in the series; wider variation lowers forecast confidence.",
        ),
        DriverContribution(
            name="latest_level_shift",
            contribution=round(max(min(level_shift, 1.0), -1.0), 6),
            direction="above_baseline" if level_shift > 0 else "below_baseline" if level_shift < 0 else "at_baseline",
            description="Difference between the latest observed value and the recent baseline.",
        ),
    ]

