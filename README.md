# OCI Forecasting MVP

Zero-shot time-series forecasting on OCI Compute with:

- `autogluon/chronos-2-small` for probabilistic forecasts and covariates
- a separate Qwen/vLLM endpoint for explanations and recommendations
- FastAPI orchestration with JSON, Markdown, and enriched CSV output
- deterministic numeric and template language fallbacks
- Python virtual environments and `systemd`, without containers

Chronos-2 is pinned to revision `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a` through `chronos-forecasting==2.3.1`. The original `amazon/chronos-t5-small` adapter remains available for environment-only rollback.

## Architecture

```text
Client
  -> forecast orchestrator :8080
       -> Chronos ML service 127.0.0.1:8081
       -> Qwen/vLLM private endpoint :8000/v1
       -> Oracle Autonomous Database (optional)
```

The orchestrator accepts one target series per request. Chronos-2 can use numeric, categorical, or boolean historical covariates and known-future covariates without training on the submitted dataset.

See [Architecture](docs/architecture.md) for the request and failure flows.

## Repository

- `ml_service/` - Chronos-2 service and deterministic fallback
- `orchestrator_api/` - public prediction and CSV APIs
- `llm_service/` - OpenAI-compatible vLLM client
- `forecast_contract.py` - shared covariate validation
- `deploy/` - installer and systemd units
- `infra/terraform/` - optional two-VM OCI scaffold
- `examples/` - sample forecast inputs
- `tests/` - unit and opt-in integration tests

## Try The Deployed API

For a private orchestrator VM, open an SSH tunnel from your laptop:

```bash
ssh -L 8080:127.0.0.1:8080 opc@<orchestrator-address>
```

Leave that terminal open. In another terminal:

```bash
curl -fsS http://127.0.0.1:8080/health | python3 -m json.tool
```

Send a covariate-aware forecast:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "demand-demo",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "past_covariates": {
      "promotion": [0, 0, 1, 1],
      "region": ["north", "north", "north", "north"]
    },
    "future_covariates": {
      "promotion": [1, 0],
      "region": ["north", "north"]
    },
    "future_timestamps": ["2026-07-05", "2026-07-06"],
    "notes": "Promotion ends after the first forecast day."
  }' | python3 -m json.tool
```

A successful response reports `ml_output.engine="chronos"`, `ml_output.model_family="chronos2"`, and the supplied names in `ml_output.covariates_used`.

## CSV And Markdown

The sample [Chronos-2 covariate CSV](examples/chronos2_covariate_test.csv) contains 12 observed rows and three trailing future rows with blank targets.

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict/csv \
  -F "file=@examples/chronos2_covariate_test.csv;type=text/csv" \
  -F "date_column=date" \
  -F "target_column=demand" \
  -F "series_id=csv-demand-demo" \
  -F "prediction_length=3" \
  -F "response_format=markdown"
```

`response_format` may be `json`, `markdown`, or `csv`. For CSV input:

- non-date/non-target columns are candidate covariates;
- trailing blank-target rows are known-future rows and must equal `prediction_length`;
- incomplete historical columns remain available to presentation and LLM context but are excluded from model input with a warning.

## Tests

The ordinary suite uses fake pipelines and does not download model weights:

```bash
./.venv/bin/python -m pytest -m 'not integration'
```

The real checkpoint test is opt-in:

```bash
python3 -m pip install -r requirements-dev.txt -r requirements-ml.txt
RUN_CHRONOS_INTEGRATION=1 python3 -m pytest -m integration tests/test_chronos_integration.py
```

## Operations

- [Chronos/vLLM Explainer](docs/chronos-vllm-explainer.md) - how numeric projections and language generation are separated
- [Runbook](docs/runbook.md) - deploy, update, smoke test, troubleshoot, rotate keys, and roll back
- [Validation](docs/validation.md) - architecture-focused smoke and non-fallback gates
- [Terraform](infra/terraform/README.md) - optional fresh two-VM OCI deployment

Do not expose port `8080` broadly without authenticated ingress. Keep Chronos port `8081` bound to localhost and the Qwen/vLLM endpoint private.
