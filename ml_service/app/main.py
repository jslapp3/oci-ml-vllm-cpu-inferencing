"""FastAPI entrypoint for the Chronos forecasting service."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .forecasting import ForecastingService
from .schemas import ForecastRequest, ForecastResponse


def create_app(service: ForecastingService | None = None) -> FastAPI:
    app = FastAPI(
        title="Chronos Forecast ML Service",
        version="0.1.0",
        description="Serves amazon/chronos-t5-small for time-series forecasting with fallback inference.",
    )
    app.state.forecasting_service = service or ForecastingService()

    @app.get("/health")
    def health() -> dict:
        return app.state.forecasting_service.health()

    @app.post("/predict", response_model=ForecastResponse)
    def predict(request: ForecastRequest) -> ForecastResponse:
        try:
            return app.state.forecasting_service.predict(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()

