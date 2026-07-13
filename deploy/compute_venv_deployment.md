# OCI Compute Venv Deployment

This is the MVP deployment path. It uses no containers, no OCIR, no OCI Data Science environment publishing, and no Object Storage dependency.

The Compute instance runs two Python services with systemd:

- `chronos-ml.service` on `127.0.0.1:8081`
- `forecast-orchestrator.service` on `0.0.0.0:8080`

## 1. OCI Prerequisites

You need:

- OCI Compute instance, preferably Oracle Linux.
- Python 3.11 if available; Python 3.10 or newer is required by `chronos-forecasting==2.3.1`.
- Outbound internet or package mirror access for `pip install`.
- Network access from the orchestrator to your vLLM endpoint.
- Optional network access to Oracle Autonomous Database.

For production access, put an OCI Load Balancer or API Gateway in front of the orchestrator rather than exposing the instance broadly.

## 2. Install The App

On the Compute instance:

```bash
git clone <your-repo-url>
cd oci-vllm-ml-inference
sudo chmod +x deploy/install_compute_venv.sh
sudo deploy/install_compute_venv.sh
```

The installer copies the repository to:

```text
/opt/oci-vllm-ml-inference
```

It creates:

```text
/opt/oci-vllm-ml-inference/.venv-ml
/opt/oci-vllm-ml-inference/.venv-orchestrator
/etc/oci-forecast/forecast.env
```

It installs:

```text
/etc/systemd/system/chronos-ml.service
/etc/systemd/system/forecast-orchestrator.service
```

The installer preserves both an existing protected environment file and `/opt/oci-vllm-ml-inference/hf_cache` across updates.

## 3. Stage The Dual-Adapter Release On The Existing Host

Do not switch the model yet. In the protected file, retain (or restore) the original model selection during the first code deployment:

```text
CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_MODEL_REVISION=
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/amazon/chronos-t5-small
ML_LOAD_PUBLIC_MODEL=true
ML_FORCE_FALLBACK=false
ML_PRELOAD_MODEL=true
HF_HOME=/opt/oci-vllm-ml-inference/hf_cache
```

Use `sudoedit` so the protected file is never printed to the terminal or copied into the repository:

```bash
sudoedit /etc/oci-forecast/forecast.env
```

Deploy the release from the existing checkout. The installer leaves `/etc/oci-forecast/forecast.env` unchanged and installs the pinned ML dependency:

```bash
cd <existing-repository-checkout>
git fetch --all --tags
git checkout <tested-release-ref>
sudo deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

Confirm that the old model still loads through the dual-adapter code:

```bash
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "legacy-regression",
    "values": [120, 127, 131, 138],
    "prediction_length": 2
  }' | python3 -m json.tool
```

The direct health response must show the original model, `model_family="chronos"`, `loaded_public_model=true`, and `load_error=null`. The prediction must keep `engine="chronos"`. Resolve any regression before changing the protected model selection.

## 4. Switch The Existing Host To Chronos-2

Edit only the named runtime entries with `sudoedit`; do not replace or print the protected file:

```text
CHRONOS_MODEL_NAME=autogluon/chronos-2-small
CHRONOS_MODEL_REVISION=ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/autogluon/chronos-2-small
CHRONOS_DEVICE=cpu
CHRONOS_NUM_SAMPLES=100
MAX_PREDICTION_LENGTH=96
ML_LOAD_PUBLIC_MODEL=true
ML_FORCE_FALLBACK=false
ML_PRELOAD_MODEL=true
HF_HOME=/opt/oci-vllm-ml-inference/hf_cache
ML_SERVICE_TIMEOUT_SECONDS=30
```

`CHRONOS_NUM_SAMPLES` is deprecated and ignored by Chronos-2; retain it only for immediate legacy rollback. Restart both services because the model/preload settings belong to the ML service and the 30-second client timeout belongs to the orchestrator:

```bash
sudoedit /etc/oci-forecast/forecast.env
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

Startup preload intentionally makes the ML health endpoint unavailable until the checkpoint is ready. It must become healthy within 300 seconds:

```bash
sudo systemctl status chronos-ml.service
sudo systemctl status forecast-orchestrator.service
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
```

The direct ML health response must show all of the following before smoke testing:

- the exact model name and revision above;
- `model_family="chronos2"`;
- `preload_attempted=true` and `preload_succeeded=true`;
- `loaded_public_model=true`;
- `load_error=null`.

Inspect service logs without logging or copying the protected environment:

```bash
journalctl -u chronos-ml.service -f
journalctl -u forecast-orchestrator.service -f
```

## 5. Smoke Test Through The Orchestrator

Run an univariate request:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "chronos2-univariate-smoke",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 2
  }' | python3 -m json.tool
```

Run a numeric and categorical covariate request:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "chronos2-covariate-smoke",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "past_covariates": {
      "promotion": [0, 0, 1, 1],
      "region": ["north", "north", "north", "north"]
    },
    "future_covariates": {
      "promotion": [1, 0],
      "region": ["north", "south"]
    },
    "future_timestamps": ["2026-07-05", "2026-07-06"],
    "notes": "Promotion starts next week and inventory is constrained."
  }' | python3 -m json.tool
```

For both responses, require `ml_output.engine="chronos"`, `ml_output.model_family="chronos2"`, the requested horizon length, finite ordered quantiles, and no ML fallback warning. The covariate response must report `covariates_used.past=["promotion","region"]` and the same names under `future` (order is alphabetical). vLLM may independently use its template fallback without invalidating the numeric model smoke test.

## 6. Benchmark And Acceptance Gates

Before enabling covariate-bearing clients, backtest both pinned configurations on representative holdout windows:

- original: `amazon/chronos-t5-small` with the original source and blank revision;
- candidate: `autogluon/chronos-2-small` at revision `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a`;
- report weighted quantile loss and MASE for each dataset/model;
- include at least one dataset with useful historical and known-future covariates;
- record dataset/window definitions, model settings, metrics, and execution date rather than overwriting prior results.

Record results in [docs/chronos_2_validation.md](../docs/chronos_2_validation.md).

Chronos-2 is not deployment-ready until all host gates pass:

- 20 consecutive smoke requests produce no deterministic fallback;
- warm p95 ML inference latency is below 20 seconds on the existing 8-OCPU E6 AX host;
- preload reaches healthy status within 300 seconds;
- peak `chronos-ml.service` RSS remains below 8 GB;
- every response has the requested horizon and finite, nondecreasing quantiles;
- covariate requests report exactly the expected `covariates_used` names.

Do not raise the OCI shape or `MAX_PREDICTION_LENGTH=96` to pass these gates. Record the result and revisit capacity separately. The opt-in checkpoint test can be run intentionally from a validation environment that has both dependency sets installed:

```bash
python3 -m pip install -r requirements-dev.txt -r requirements-ml.txt
RUN_CHRONOS_INTEGRATION=1 python3 -m pytest -m integration tests/test_chronos_integration.py
```

Do not set `RUN_CHRONOS_INTEGRATION` during ordinary unit tests.

## 7. Exact Environment-Only Rollback

Rollback does not require a code change, dependency reinstall, orchestrator restart, shape change, or port change. With `sudoedit /etc/oci-forecast/forecast.env`, restore exactly these three entries:

```text
CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_MODEL_REVISION=
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/amazon/chronos-t5-small
```

Then restart only the ML service and verify the retained adapter:

```bash
sudoedit /etc/oci-forecast/forecast.env
sudo systemctl restart chronos-ml.service
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{"series_id":"rollback-smoke","values":[120,127,131,138],"prediction_length":2}' \
  | python3 -m json.tool
```

Require health to show `model_name="amazon/chronos-t5-small"`, `model_family="chronos"`, `loaded_public_model=true`, and `load_error=null`; require the smoke response to retain `engine="chronos"`. Covariates are intentionally unsupported on the rollback adapter.

## 8. Later App Updates

From a fresh checkout on the Compute instance:

```bash
sudo deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

The installer leaves an existing `/etc/oci-forecast/forecast.env` unchanged.

## 9. Hardening Notes

For MVP, environment variables live in `/etc/oci-forecast/forecast.env`.

For production:

- Move secrets to OCI Vault.
- Put the instance in a private subnet.
- Use Load Balancer or API Gateway in front of the orchestrator.
- Keep `chronos-ml.service` bound to `127.0.0.1`.
- Export `journalctl` logs to OCI Logging.
- Consider conda or packed conda environments if Python dependency reproducibility becomes painful.
