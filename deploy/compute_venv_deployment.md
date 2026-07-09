# OCI Compute Venv Deployment

This is the MVP deployment path. It uses no containers, no OCIR, no OCI Data Science environment publishing, and no Object Storage dependency.

The Compute instance runs two Python services with systemd:

- `chronos-ml.service` on `127.0.0.1:8081`
- `forecast-orchestrator.service` on `0.0.0.0:8080`

## 1. OCI Prerequisites

You need:

- OCI Compute instance, preferably Oracle Linux.
- Python 3.11 if available; Python 3 is the fallback.
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

## 3. Configure Runtime Settings

Edit:

```bash
sudo vi /etc/oci-forecast/forecast.env
```

For first smoke tests, keep fallback mode:

```text
ML_LOAD_PUBLIC_MODEL=false
ML_FORCE_FALLBACK=true
```

For real Chronos inference:

```text
ML_LOAD_PUBLIC_MODEL=true
ML_FORCE_FALLBACK=false
```

Set `VLLM_BASE_URL` to your OCI-hosted vLLM endpoint:

```text
VLLM_BASE_URL=http://<vllm-private-ip-or-dns>:8000/v1
```

## 4. Start Services

```bash
sudo systemctl start chronos-ml.service
sudo systemctl start forecast-orchestrator.service
```

Check status:

```bash
sudo systemctl status chronos-ml.service
sudo systemctl status forecast-orchestrator.service
```

Logs:

```bash
journalctl -u chronos-ml.service -f
journalctl -u forecast-orchestrator.service -f
```

## 5. Smoke Test

Health:

```bash
curl http://127.0.0.1:8080/health
```

Prediction:

```bash
curl -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "demo-demand-series",
    "values": [120, 127, 131, 138],
    "prediction_length": 6,
    "notes": "Promotion starts next week and inventory is constrained."
  }'
```

If vLLM is not reachable yet, the orchestrator should still return a forecast and template fallback explanation.

## 6. Update The App

From a fresh checkout on the Compute instance:

```bash
sudo deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

The installer leaves an existing `/etc/oci-forecast/forecast.env` unchanged.

## 7. Hardening Notes

For MVP, environment variables live in `/etc/oci-forecast/forecast.env`.

For production:

- Move secrets to OCI Vault.
- Put the instance in a private subnet.
- Use Load Balancer or API Gateway in front of the orchestrator.
- Keep `chronos-ml.service` bound to `127.0.0.1`.
- Export `journalctl` logs to OCI Logging.
- Consider conda or packed conda environments if Python dependency reproducibility becomes painful.

