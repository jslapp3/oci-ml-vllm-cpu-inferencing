# OCI vLLM ML Inference

MVP OCI inference scaffold using a public pretrained forecasting model, two Python services on OCI Compute, and a vLLM companion endpoint.

Selected non-vLLM model: `amazon/chronos-t5-small`.

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

Full deployment instructions are in [deploy/compute_venv_deployment.md](deploy/compute_venv_deployment.md).

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
- Copies systemd unit files
- Creates `/etc/oci-forecast/forecast.env` if it does not exist
- Enables both services

For first smoke tests, the env template defaults to fallback mode:

```text
ML_LOAD_PUBLIC_MODEL=false
ML_FORCE_FALLBACK=true
```

For real Chronos inference, edit `/etc/oci-forecast/forecast.env`:

```text
ML_LOAD_PUBLIC_MODEL=true
ML_FORCE_FALLBACK=false
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
    "notes": "Promotion starts next week and inventory is constrained.",
    "metadata": {"domain": "demand"}
  }'
```

Service logs:

```bash
journalctl -u chronos-ml.service -f
journalctl -u forecast-orchestrator.service -f
```

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

The tests do not download Chronos. They exercise fallback behavior, response shape, vLLM fallback, orchestration, and disabled DB writes.

