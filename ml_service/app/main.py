"""FastAPI entrypoint for the Chronos forecasting service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .forecasting import ForecastingService
from .schemas import ForecastRequest, ForecastResponse


def create_app(service: ForecastingService | None = None) -> FastAPI:
    forecasting_service = service or ForecastingService()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if forecasting_service.settings.preload_model:
            forecasting_service.preload()
        yield

    app = FastAPI(
        title="Chronos Forecast ML Service",
        version="0.2.0",
        description="Serves Chronos-2 or legacy Chronos for zero-shot forecasting with fallback inference.",
        lifespan=lifespan,
    )
    app.state.forecasting_service = forecasting_service

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
