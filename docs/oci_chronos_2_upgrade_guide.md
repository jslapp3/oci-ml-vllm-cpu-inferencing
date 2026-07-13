# OCI Chronos-2 Existing-Host Upgrade

This guide upgrades the existing orchestrator VM from `amazon/chronos-t5-small` to `autogluon/chronos-2-small`.

Only the orchestrator VM changes. Do not update or restart the separate Qwen/vLLM VM. Preserve the existing `VLLM_*`, database, and credential entries in `/etc/oci-forecast/forecast.env`.

No Terraform apply, VM replacement, shape change, port change, or security-list change is required.

## 1. Publish The Code

Run the non-integration tests on the laptop:

```bash
cd /Users/jacoblapp/Desktop/oci-vllm-ml-inference
./.venv/bin/python -m pytest -m 'not integration'
```

Commit and push the migration. `git add -u` stages modified tracked files; the second command stages the new migration files without adding unrelated untracked datasets.

```bash
git add -u
git add forecast_contract.py \
  docs/chronos_2_migration_plan.md \
  docs/chronos_2_validation.md \
  docs/oci_chronos_2_upgrade_guide.md \
  tests/test_chronos_adapters.py \
  tests/test_chronos_integration.py \
  tests/test_forecast_contract.py
git commit -m "Migrate forecasting service to Chronos-2 small"
git push origin HEAD
git rev-parse HEAD
```

Save the commit SHA printed by the last command.

## 2. Get That Commit On The Orchestrator VM

Use `git fetch`, not `git pull`. Fetch downloads the commit without merging or rebasing the host's current branch. Checking out the tested SHA makes the deployment exact and reproducible.

SSH to the orchestrator VM and use the existing source checkout outside `/opt/oci-vllm-ml-inference`:

```bash
ssh <oci-user>@<orchestrator-address>
cd <existing-source-checkout>
git fetch origin
git checkout <tested-commit-sha>
```

Do not run the installer from `/opt/oci-vllm-ml-inference`; that directory is the install target and is replaced during deployment.

Back up the protected environment without printing it:

```bash
sudo cp -p /etc/oci-forecast/forecast.env /etc/oci-forecast/forecast.env.pre-chronos2
sudo chmod 600 /etc/oci-forecast/forecast.env.pre-chronos2
```

## 3. Deploy The New Code With Old Chronos

First deploy the dual-adapter code while retaining the original model. Edit the protected file:

```bash
sudoedit /etc/oci-forecast/forecast.env
```

Set or update only these entries. Leave every existing `VLLM_*` and credential entry unchanged.

```text
CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_MODEL_REVISION=
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/amazon/chronos-t5-small
CHRONOS_DEVICE=cpu
CHRONOS_NUM_SAMPLES=100
MAX_PREDICTION_LENGTH=96
ML_LOAD_PUBLIC_MODEL=true
ML_FORCE_FALLBACK=false
ML_PRELOAD_MODEL=true
HF_HOME=/opt/oci-vllm-ml-inference/hf_cache
ML_SERVICE_TIMEOUT_SECONDS=30
```

Install the release and restart both orchestrator-VM services:

```bash
sudo deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

Verify the original adapter still works:

```bash
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{"series_id":"legacy-smoke","values":[120,127,131,138],"prediction_length":2}' \
  | python3 -m json.tool
```

Continue only if health reports `model_family="chronos"`, `loaded_public_model=true`, and `load_error=null`, and the prediction reports `ml_output.engine="chronos"`.

## 4. Switch To Chronos-2

Edit the same protected file:

```bash
sudoedit /etc/oci-forecast/forecast.env
```

Replace only the three model-selection entries:

```text
CHRONOS_MODEL_NAME=autogluon/chronos-2-small
CHRONOS_MODEL_REVISION=ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/autogluon/chronos-2-small
```

Restart both services:

```bash
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

The first start downloads and preloads the pinned model. Follow progress:

```bash
journalctl -u chronos-ml.service -f
```

When startup finishes, verify health:

```bash
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
```

Require:

- `model_family="chronos2"`
- `preload_succeeded=true`
- `loaded_public_model=true`
- `load_error=null`

## 5. Smoke Test Chronos-2

Run one request through the orchestrator that exercises historical and future covariates:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "chronos2-smoke",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "past_covariates": {
      "promotion": [0, 0, 1, 1]
    },
    "future_covariates": {
      "promotion": [1, 0]
    },
    "future_timestamps": ["2026-07-05", "2026-07-06"]
  }' | python3 -m json.tool
```

Require `ml_output.engine="chronos"`, `ml_output.model_family="chronos2"`, two forecast points, no ML fallback warning, and `promotion` under both `covariates_used.past` and `covariates_used.future`.

The Qwen explanation may independently use its template fallback without invalidating the Chronos-2 numeric forecast.

## 6. Roll Back If Needed

To return to original Chronos, restore these three entries with `sudoedit /etc/oci-forecast/forecast.env`:

```text
CHRONOS_MODEL_NAME=amazon/chronos-t5-small
CHRONOS_MODEL_REVISION=
CHRONOS_MODEL_SOURCE_URL=https://huggingface.co/amazon/chronos-t5-small
```

Restart only the ML service and verify it:

```bash
sudo systemctl restart chronos-ml.service
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
```

Rollback is successful when health reports `model_family="chronos"`, `loaded_public_model=true`, and `load_error=null`. No code rollback or Qwen VM change is required.
