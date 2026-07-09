# Architecture

This MVP runs as a no-container cloud application on OCI Compute.

Core components:

1. `ml_service/` serves the selected public forecasting model, `amazon/chronos-t5-small`.
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
2. The orchestrator forwards time-series values to `http://127.0.0.1:8081/predict`.
3. The ML service loads Chronos lazily and returns forecast points, risk summary, confidence, and proxy drivers.
4. The orchestrator asks the vLLM companion endpoint for explanation text and recommended next actions.
5. If configured, the orchestrator writes the run to Oracle Autonomous Database.
6. The combined response is returned to the caller.

## Failure Behavior

- If Chronos cannot load, `ml_service` uses a deterministic fallback trend model and marks the response.
- If vLLM is unavailable, the orchestrator returns template-based explanation and recommendations.
- If ADB logging fails, the API response still succeeds and includes the database write error.

## Hardening Path

This MVP deliberately starts with `venv` plus `systemd`. Later hardening options:

- Conda environment files or packed conda environments for more stable Torch/Chronos installs.
- Object Storage to store environment archives.
- OCI Data Science Model Deployment for managed model serving.
- Containers and OCIR if image-based promotion becomes useful later.

