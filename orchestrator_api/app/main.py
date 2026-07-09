"""FastAPI orchestrator coordinating ML forecasting, vLLM, and optional ADB logging."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from httpx import HTTPError

from llm_service.app.client import VLLMCompanionClient

from .db import DatabaseWriter
from .ml_client import MLServiceClient
from .schemas import CombinedPredictionResponse, PredictionRequest


def create_app(
    ml_client: Optional[MLServiceClient] = None,
    llm_client: Optional[VLLMCompanionClient] = None,
    db_writer: Optional[DatabaseWriter] = None,
) -> FastAPI:
    app = FastAPI(
        title="OCI Forecast Orchestrator API",
        version="0.1.0",
        description="Coordinates Chronos forecasting, vLLM explanations, and optional Oracle ADB logging.",
    )
    app.state.ml_client = ml_client or MLServiceClient()
    app.state.llm_client = llm_client or VLLMCompanionClient()
    app.state.db_writer = db_writer or DatabaseWriter()

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "ml_service_base_url": app.state.ml_client.settings.ml_service_base_url,
            "db_enabled": app.state.db_writer.enabled,
        }

    @app.post("/predict", response_model=CombinedPredictionResponse)
    async def predict(request: PredictionRequest) -> CombinedPredictionResponse:
        run_id = str(uuid.uuid4())
        ml_payload = _ml_payload(request)
        warnings = []

        try:
            ml_output = await app.state.ml_client.predict(ml_payload)
        except HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"ML service unavailable: {exc}") from exc

        extracted_features = await app.state.llm_client.extract_structured_features(request.notes)
        explanation = await app.state.llm_client.generate_explanation(ml_output, request.notes)
        recommendations = await app.state.llm_client.generate_recommendations(ml_output, request.notes)

        if not explanation.get("available"):
            warnings.append("vLLM explanation unavailable; template fallback used")
        if not recommendations.get("available"):
            warnings.append("vLLM recommendations unavailable; template fallback used")

        response_payload: Dict[str, Any] = {
            "run_id": run_id,
            "status": "completed",
            "ml_output": ml_output,
            "explanation": explanation,
            "recommendations": recommendations,
            "extracted_features": extracted_features,
            "database_write": {"enabled": False, "wrote": False, "error": None},
            "warnings": warnings,
        }
        database_write = await app.state.db_writer.write_inference_run(run_id, _dump_model(request), response_payload)
        response_payload["database_write"] = database_write
        return CombinedPredictionResponse(**response_payload)

    return app


def _ml_payload(request: PredictionRequest) -> Dict[str, Any]:
    payload = _dump_model(request, exclude_none=True)
    payload.pop("notes", None)
    return payload


def _dump_model(model, **kwargs) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


app = create_app()
