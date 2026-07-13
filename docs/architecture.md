# Architecture

This MVP runs as a no-container cloud application on OCI Compute. Runtime commands, model settings, and rollback procedures live in the [operations runbook](runbook.md).

Core components:

1. `ml_service/` serves the selected public forecasting model, `autogluon/chronos-2-small`, while retaining the original `amazon/chronos-t5-small` adapter for rollback.
2. `llm_service/` provides a client for a vLLM OpenAI-compatible endpoint.
3. `orchestrator_api/` coordinates the forecast, LLM explanation, recommendations, optional text feature extraction, and optional ADB logging.

vLLM is intentionally not used to serve the forecasting model. The numeric time-series model runs in its own FastAPI service, while vLLM handles language tasks around the model output.

## Runtime Topology

```text
Client / APEX / Oracle Analytics / API consumer
  -> OCI Load Balancer or API Gateway
  -> OCI Compute instance
  -> forecast-orchestrator.service on 0.0.0.0:8080
  -> chronos-ml.service on 127.0.0.1:8081
  -> vLLM OpenAI-compatible endpoint
  -> Oracle Autonomous Database, optional
```

The services are managed by `systemd`:

- `chronos-ml.service` runs from `/opt/oci-vllm-ml-inference/.venv-ml`.
- `forecast-orchestrator.service` runs from `/opt/oci-vllm-ml-inference/.venv-orchestrator`.
- Runtime configuration lives in `/etc/oci-forecast/forecast.env`.

## Request Flow

1. A consumer calls `POST /predict` on the orchestrator.
2. The orchestrator validates and forwards the target, timestamps, optional historical covariates, optional known-future covariates, and future timestamps to `http://127.0.0.1:8081/predict`.
3. The ML service preloads the configured checkpoint at startup by default. `BaseChronosPipeline` identifies the loaded family: Chronos-2 uses its dataframe/quantile adapter, while original Chronos uses the retained sample-based tensor adapter.
4. Chronos-2 receives one target series on an internal regular daily index. Supplied timestamps remain response labels; irregular timestamps generate a warning and are treated as ordered, equally spaced observations.
5. The ML service returns forecast points, risk summary, confidence, heuristic drivers, `model_family`, and the historical/future covariate names actually used.
6. The orchestrator asks the vLLM companion endpoint for explanation text and recommended next actions.
7. If configured, the orchestrator writes the run to Oracle Autonomous Database.
8. The combined response is returned to the caller as JSON, Markdown, or enriched CSV where applicable.

Chronos-2 remains zero-shot. There is no per-dataset training, fine-tuning, AutoGluon-TimeSeries dependency, multivariate target, or multi-series batch API.

## CSV Covariate Flow

- Every non-date/non-target column remains a candidate covariate and presentation field.
- Contiguous trailing blank-target rows are future rows and must exactly match the requested horizon.
- History-complete columns are sent as past covariates. If also complete in future rows, they are sent as known-future covariates.
- History-incomplete columns are excluded from model input with a warning but retained in summaries, LLM context, and enriched output.
- Blank targets inside the historical portion retain the previous skip-and-warn behavior.

## Failure Behavior

- If Chronos cannot load, `ml_service` uses a deterministic fallback trend model and marks the response.
- If either Chronos adapter fails or emits invalid/non-finite/unordered quantiles, the same fallback is used.
- The deterministic fallback ignores covariates and says so explicitly. The original Chronos adapter also warns if covariates were supplied because rollback inference remains univariate.
- If vLLM is unavailable, the orchestrator returns template-based explanation and recommendations.
- If ADB logging fails, the API response still succeeds and includes the database write error.

## Hardening Path

The pinned model uses CPU float32, a maximum horizon of 96, a persistent cache at `/opt/oci-vllm-ml-inference/hf_cache`, and a 300-second systemd startup ceiling. This MVP deliberately starts with `venv` plus `systemd`. Later hardening options:

- Conda environment files or packed conda environments for more stable Torch/Chronos installs.
- Object Storage to store environment archives.
- OCI Data Science Model Deployment for managed model serving.
- Containers and OCIR if image-based promotion becomes useful later.
