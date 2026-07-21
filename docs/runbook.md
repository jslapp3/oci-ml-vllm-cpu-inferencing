# Operations Runbook

This runbook covers the deployed two-VM MVP:

```text
Public or tunneled client
  -> orchestrator VM :8080
       -> Chronos-2 127.0.0.1:8081
       -> private Qwen/vLLM VM :8000/v1
```

The Qwen VM does not need to change during ordinary orchestrator deployments.

Quick test from a laptop: run `ssh -L 8080:127.0.0.1:8080 opc@<orchestrator-address>` and leave it open, then call `curl -fsS http://127.0.0.1:8080/health` from a second terminal.

## Host Paths

| Purpose | Path |
| --- | --- |
| Installed application | `/opt/oci-vllm-ml-inference` |
| Chronos virtual environment | `/opt/oci-vllm-ml-inference/.venv-ml` |
| Orchestrator virtual environment | `/opt/oci-vllm-ml-inference/.venv-orchestrator` |
| Hugging Face cache | `/opt/oci-vllm-ml-inference/hf_cache` |
| Protected runtime configuration | `/etc/oci-forecast/forecast.env` |
| Chronos service | `chronos-ml.service` |
| Orchestrator service | `forecast-orchestrator.service` |
| Qwen service | `vllm-openai.service` |

Never print or commit the protected environment files. Use `sudoedit`.

## Install Or Update The Orchestrator VM

The host requires Python 3.11. Python 3.9 cannot install the pinned Chronos package.

```bash
python3.11 --version
```

On Oracle Linux, install it if needed:

```bash
sudo dnf install -y python3.11 python3.11-pip
```

Use a source checkout outside `/opt/oci-vllm-ml-inference`; the installer replaces the contents of `/opt` while preserving the model cache.

Deploy an exact tested commit rather than merging the host branch:

```bash
cd <source-checkout>
git fetch origin
git checkout <tested-commit-sha>
sudo env PYTHON_BIN=python3.11 deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

The installer preserves `/etc/oci-forecast/forecast.env` and `/opt/oci-vllm-ml-inference/hf_cache`. Use `git fetch` plus an exact SHA for reproducible deployments; `git pull` is unnecessary.

For a first installation, review the generated environment before starting services:

```bash
sudoedit /etc/oci-forecast/forecast.env
```

The core ML settings are:

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
ML_SERVICE_BASE_URL=http://127.0.0.1:8081
ML_SERVICE_TIMEOUT_SECONDS=30
```

`CHRONOS_NUM_SAMPLES` is used only by the original Chronos rollback adapter. Preserve the working `VLLM_*`, database, and credential entries when editing this file.

## Verify Services

```bash
sudo systemctl --no-pager --full status chronos-ml.service
sudo systemctl --no-pager --full status forecast-orchestrator.service
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8080/health | python3 -m json.tool
```

Chronos-2 health should report:

```text
model_family: chronos2
preload_succeeded: true
loaded_public_model: true
load_error: null
```

The first start may download and preload the checkpoint. Follow progress with:

```bash
journalctl -u chronos-ml.service -f
```

Other useful logs:

```bash
journalctl -u chronos-ml.service --since '-15 minutes' --no-pager
journalctl -u forecast-orchestrator.service --since '-15 minutes' --no-pager
```

## Smoke Test

From the orchestrator VM:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "chronos2-smoke",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "past_covariates": {"promotion": [0, 0, 1, 1]},
    "future_covariates": {"promotion": [1, 0]},
    "future_timestamps": ["2026-07-05", "2026-07-06"],
    "notes": "Promotion ends after the first forecast day."
  }' | python3 -m json.tool
```

Require `ml_output.engine="chronos"`, `ml_output.model_family="chronos2"`, the requested horizon, no ML fallback warning, and `promotion` in both covariate lists. A Qwen template fallback does not invalidate the numeric forecast, but it should be investigated separately.

## Access From A Laptop

Open a tunnel and leave it running:

```bash
ssh -L 8080:127.0.0.1:8080 opc@<orchestrator-address>
```

Then use `http://127.0.0.1:8080` locally. This avoids exposing the unauthenticated MVP API directly to the internet.

To reach a private Qwen VM through the orchestrator:

```bash
ssh -J opc@<orchestrator-address> opc@<qwen-private-ip>
```

## Roll Back To Original Chronos

Edit `/etc/oci-forecast/forecast.env` and change only:

```text
CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_MODEL_REVISION=
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/amazon/chronos-t5-small
```

Restart only the ML service:

```bash
sudo systemctl restart chronos-ml.service
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
```

Rollback succeeds when health reports `model_family="chronos"`, `loaded_public_model=true`, and `load_error=null`. The original adapter ignores covariates with a warning.

## Rotate The Qwen API Key

Generate a key on the laptop and keep it out of chat, Git, and shell history:

```bash
openssl rand -hex 32
```

Jump to the private Qwen VM:

```bash
ssh -J opc@<orchestrator-address> opc@<qwen-private-ip>
sudoedit /etc/vllm/vllm.env
sudo systemctl restart vllm-openai.service
```

Set `VLLM_API_KEY` to the new value. Test without placing it in history:

```bash
read -rsp 'New vLLM key: ' VLLM_KEY
echo
curl -fsS http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer $VLLM_KEY" \
  | python3 -m json.tool
unset VLLM_KEY
```

Then update the same `VLLM_API_KEY` in `/etc/oci-forecast/forecast.env` on the orchestrator VM and restart only:

```bash
sudo systemctl restart forecast-orchestrator.service
```

Run the smoke test and require `explanation.available=true`, `explanation.used_fallback=false`, and equivalent recommendation fields.

## Troubleshooting

### Chronos package will not install

If pip reports that `chronos-forecasting==2.3.1` has no matching distribution and the virtual environment path contains `python3.9`, install Python 3.11 and rerun the installer with `PYTHON_BIN=python3.11`.

### Health is unavailable after restart

Preload keeps the ML endpoint unavailable while the checkpoint loads. Check `journalctl -u chronos-ml.service -f` and allow up to the service's 300-second startup limit.

### vLLM returns 401

Confirm the Qwen service is active and that `/etc/vllm/vllm.env` and `/etc/oci-forecast/forecast.env` contain the same key. Restart `vllm-openai.service` after changing the Qwen file and `forecast-orchestrator.service` after changing the orchestrator file.

### Forecast uses fallback

Inspect `ml_output.warnings`, `model_family`, and the Chronos journal. Deterministic fallback keeps the API available but ignores covariates.

## Production Follow-Ups

The current deployment is a working MVP. Before broader exposure:

- complete [the validation record](validation.md);
- rotate any disclosed secrets and move secrets to OCI Vault;
- add authenticated ingress through API Gateway or a load balancer;
- export service logs and fallback metrics to OCI Logging;
- keep Chronos on localhost and Qwen in its private subnet.
