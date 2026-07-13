# OCI vLLM ML Inference

MVP OCI inference scaffold using a public pretrained forecasting model, two Python services on OCI Compute, and a vLLM companion endpoint.

Selected non-vLLM model: `autogluon/chronos-2-small`, pinned to revision
`ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a` with `chronos-forecasting==2.3.1`.
The original `amazon/chronos-t5-small` adapter remains available as an environment-only rollback path.

The forecasting model is served separately from vLLM. Chronos handles numeric time-series forecasting; vLLM handles explanation text, recommendations, and optional text-derived features around the forecast.

No local Docker, Podman, OCIR, or OCI Data Science environment publishing is required for the MVP.

## MVP Architecture

```text
Client / APEX / Oracle Analytics / API consumer
  -> OCI Load Balancer or API Gateway
  -> OCI Compute instance
  -> systemd: forecast-orchestrator.service on port 8080
  -> systemd: chronos-ml.service on 127.0.0.1:8081
  -> vLLM OpenAI-compatible endpoint, separately hosted
  -> Oracle Autonomous Database, optional logging
```

The two FastAPI apps run as regular Linux services:

- `chronos-ml.service` uses `.venv-ml` and serves the Chronos forecasting API.
- `forecast-orchestrator.service` uses `.venv-orchestrator` and exposes the public orchestration API.

## Layout

- `ml_service/` - FastAPI service for Chronos time-series forecasting.
- `llm_service/` - vLLM OpenAI-compatible client package.
- `orchestrator_api/` - FastAPI API coordinating ML, vLLM, and optional ADB logging.
- `requirements-ml.txt` - dependencies for the ML service venv.
- `requirements-orchestrator.txt` - dependencies for the orchestrator venv.
- `db/` - Oracle Autonomous Database schema and seed SQL.
- `deploy/` - OCI Compute, venv, and systemd deployment assets.
- `docs/` - architecture and selected model notes.
- `tests/` - focused pytest coverage.

## OCI Compute Deployment

Full deployment instructions are in [deploy/compute_venv_deployment.md](deploy/compute_venv_deployment.md). For upgrading an existing OCI host to Chronos-2, use the focused [OCI Chronos-2 upgrade guide](docs/oci_chronos_2_upgrade_guide.md).

On the OCI Compute instance:

```bash
git clone <your-repo-url>
cd oci-vllm-ml-inference
sudo chmod +x deploy/install_compute_venv.sh
sudo deploy/install_compute_venv.sh
```

The installer:

- Copies the app to `/opt/oci-vllm-ml-inference`
- Creates `/opt/oci-vllm-ml-inference/.venv-ml`
- Creates `/opt/oci-vllm-ml-inference/.venv-orchestrator`
- Creates and preserves `/opt/oci-vllm-ml-inference/hf_cache`
- Copies systemd unit files
- Creates `/etc/oci-forecast/forecast.env` if it does not exist
- Enables both services

New installations default to pinned Chronos-2 with startup preload:

```text
CHRONOS_MODEL_NAME=autogluon/chronos-2-small
CHRONOS_MODEL_REVISION=ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a
ML_LOAD_PUBLIC_MODEL=true
ML_FORCE_FALLBACK=false
ML_PRELOAD_MODEL=true
```

Use deterministic fallback only for diagnostics:

```text
ML_FORCE_FALLBACK=true
```

Then start:

```bash
sudo systemctl start chronos-ml.service
sudo systemctl start forecast-orchestrator.service
```

## Health And Prediction

On the Compute instance:

```bash
curl http://127.0.0.1:8080/health
```

Prediction:

```bash
curl -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "demo-demand-series",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 6,
    "past_covariates": {
      "promotion": [0, 0, 0, 1],
      "region": ["north", "north", "north", "north"]
    },
    "future_covariates": {
      "promotion": [1, 1, 1, 0, 0, 0],
      "region": ["north", "north", "north", "north", "north", "north"]
    },
    "future_timestamps": [
      "2026-07-05", "2026-07-06", "2026-07-07",
      "2026-07-08", "2026-07-09", "2026-07-10"
    ],
    "notes": "Promotion starts next week and inventory is constrained.",
    "metadata": {"domain": "demand"}
  }'
```

Service logs:

```bash
journalctl -u chronos-ml.service -f
journalctl -u forecast-orchestrator.service -f
```

## CSV Upload And Pretty Output

The public orchestrator also accepts CSV uploads through:

```text
POST /predict/csv
```

Example CSV:

```csv
date,demand,promo_flag,inventory
2026-07-01,120,0,450
2026-07-02,127,0,430
2026-07-03,131,1,410
2026-07-04,,1,400
2026-07-05,,0,390
```

From a laptop:

```bash
curl --noproxy '*' -sS -i \
  -X POST http://<orchestrator-public-ip>:8080/predict/csv \
  -F "file=@demand.csv" \
  -F "date_column=date" \
  -F "target_column=demand" \
  -F "series_id=store-42-demand" \
  -F "prediction_length=2" \
  -F "notes=Promotion starts next week and inventory is constrained."
```

For terminal-friendly output, request Markdown instead of the full JSON payload:

```bash
curl --noproxy '*' -sS \
  -X POST http://<orchestrator-public-ip>:8080/predict/csv \
  -F "file=@demand.csv" \
  -F "date_column=date" \
  -F "target_column=demand" \
  -F "series_id=store-42-demand" \
  -F "prediction_length=2" \
  -F "notes=Promotion starts next week and inventory is constrained." \
  -F "response_format=markdown"
```

To download an enriched CSV directly, use:

```bash
curl --noproxy '*' -sS \
  -X POST http://<orchestrator-public-ip>:8080/predict/csv \
  -F "file=@demand.csv" \
  -F "date_column=date" \
  -F "target_column=demand" \
  -F "series_id=store-42-demand" \
  -F "prediction_length=2" \
  -F "notes=Promotion starts next week and inventory is constrained." \
  -F "response_format=csv" \
  -o forecast_enriched.csv
```

Complete non-date/non-target columns are sent to Chronos-2 as historical covariates. A contiguous suffix of blank-target rows must equal `prediction_length`; complete columns in that suffix become known-future covariates. Historically incomplete columns are excluded from model input with a warning but remain in metadata, LLM context, and enriched CSV output. Columns that are complete in history but incomplete in future remain past-only.

ML responses keep `engine="chronos"` for either real Chronos family and add `model_family` plus `covariates_used`. Deterministic fallback keeps `engine="fallback"`, reports `model_family="fallback"`, ignores covariates, and emits an explicit warning. `drivers` remain inexpensive heuristics based on the target history, not Chronos-2 feature attribution.

All prediction responses include a `presentation` object with:

- `predictions_text` - newline/star formatted forecast values.
- `explanation_paragraph` - readable explanation text.
- `recommendations_text` - readable next actions.
- `enriched_csv` - for CSV uploads, original actuals plus forecast rows and explanation text as CSV.

## vLLM Endpoint

The orchestrator expects an OpenAI-compatible vLLM endpoint:

```text
VLLM_BASE_URL=http://<vllm-private-ip-or-dns>:8000/v1
VLLM_MODEL=meta-llama/Llama-3.1-8B-Instruct
VLLM_API_KEY=EMPTY
```

If vLLM is unavailable, the API still returns a forecast with template-based explanation and recommendations.

## Tests

Tests can run from any Python environment:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

The ordinary suite uses fake pipelines and does not download model weights. The pinned CPU checkpoint smoke test is separately marked and opt-in:

```bash
python3 -m pip install -r requirements-dev.txt -r requirements-ml.txt
RUN_CHRONOS_INTEGRATION=1 python3 -m pytest -m integration tests/test_chronos_integration.py
```

Run that integration test, backtests, and the E6 AX acceptance gates only during an intentional deployment validation. Record them in [docs/chronos_2_validation.md](docs/chronos_2_validation.md). See [deploy/compute_venv_deployment.md](deploy/compute_venv_deployment.md) for staged rollout and exact rollback instructions.
