# Scenario 02: AMD To Intel Migration

## Intent

Prove that the private vLLM inferencing VM can migrate from AMD to Intel while preserving the same service contract:

```text
http://<vllm-private-ip>:8000/v1
```

The orchestrator should not need application code changes if the endpoint URL remains stable.

## Expected Change Surface

| Layer | Expected change |
| --- | --- |
| App code | None. |
| Orchestrator config | None if `VLLM_BASE_URL` stays the same. |
| vLLM systemd command | Usually none. |
| vLLM cloud-init | None for in-place migration; reused for rebuild. |
| Terraform | Change vLLM shape to Intel target. |
| OCI runtime | Instance shape, CPU flags, performance characteristics. |

## Target Intel Shape

Default target:

```hcl
vllm_shape = "VM.Standard4.Ax.Flex"
```

Keep private IP stable where possible:

```hcl
vllm_private_ip = "10.0.1.98"
```

## Migration Validation

On the vLLM VM:

```bash
lscpu
sudo systemctl --no-pager --full status vllm-openai.service
```

From the orchestrator VM:

```bash
curl -fsS http://<vllm-private-ip>:8000/v1/models \
  -H "Authorization: Bearer <redacted-key>" | python3 -m json.tool
```

Through the orchestrator:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "scenario-02-intel-migration",
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "notes": "Intel vLLM migration validation."
  }' | python3 -m json.tool
```

## Results

Pending.

## Known Gaps

- Need to confirm OCI capacity/quota for `VM.Standard4.Ax.Flex`.
- Need to confirm whether Terraform plans in-place update or replacement for the selected migration path.
- If replacement is required, preserve private IP or update `VLLM_BASE_URL` accordingly.
