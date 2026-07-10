"""FastAPI orchestrator coordinating ML forecasting, vLLM, and optional ADB logging."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from httpx import HTTPError
from pydantic import ValidationError

from llm_service.app.client import VLLMCompanionClient

from .csv_input import CsvForecastData, CsvInputError, csv_context_notes, parse_csv_forecast_upload, parse_quantile_levels
from .db import DatabaseWriter
from .ml_client import MLServiceClient
from .presentation import build_presentation
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
        return await _run_prediction(app, request)

    @app.post("/predict/csv", response_model=CombinedPredictionResponse)
    async def predict_csv(
        file: UploadFile = File(...),
        date_column: str = Form("date"),
        target_column: str = Form("target"),
        series_id: str = Form("csv-series"),
        prediction_length: int = Form(12),
        notes: Optional[str] = Form(None),
        quantile_levels: str = Form("0.1,0.5,0.9"),
    ) -> CombinedPredictionResponse:
        if prediction_length < 1:
            raise HTTPException(status_code=400, detail="prediction_length must be at least 1")

        try:
            csv_data = parse_csv_forecast_upload(
                await file.read(),
                filename=file.filename,
                date_column=date_column,
                target_column=target_column,
            )
            request = PredictionRequest(
                series_id=series_id,
                timestamps=csv_data.timestamps,
                values=csv_data.values,
                prediction_length=prediction_length,
                quantile_levels=parse_quantile_levels(quantile_levels),
                notes=csv_context_notes(notes, csv_data),
                metadata=csv_data.metadata(),
            )
        except CsvInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors()) from exc

        return await _run_prediction(app, request, csv_data=csv_data)

    return app


async def _run_prediction(
    app: FastAPI,
    request: PredictionRequest,
    csv_data: Optional[CsvForecastData] = None,
) -> CombinedPredictionResponse:
    run_id = str(uuid.uuid4())
    ml_payload = _ml_payload(request)
    warnings = list(csv_data.warnings if csv_data else [])

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
        "presentation": build_presentation(
            ml_output=ml_output,
            explanation=explanation,
            recommendations=recommendations,
            csv_data=csv_data,
        ),
        "database_write": {"enabled": False, "wrote": False, "error": None},
        "warnings": warnings,
    }
    database_write = await app.state.db_writer.write_inference_run(run_id, _dump_model(request), response_payload)
    response_payload["database_write"] = database_write
    return CombinedPredictionResponse(**response_payload)


def _ml_payload(request: PredictionRequest) -> Dict[str, Any]:
    payload = _dump_model(request, exclude_none=True)
    payload.pop("notes", None)
    return payload


def _dump_model(model, **kwargs) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


app = create_app()
