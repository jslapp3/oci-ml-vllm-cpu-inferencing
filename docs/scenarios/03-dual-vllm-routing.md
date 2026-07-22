# Scenario 03: Dual vLLM Routing

Status: **Planned.** Scenarios 01 and 02 are complete and available as separate
AMD and Intel reference deployments.

## Intent

Prove that one deployment can run both AMD and Intel vLLM endpoints and route language-generation calls between them.

Chronos numeric forecasting remains unchanged.

## Starting Point

- Scenario 01 AMD is validated in Terraform workspace `default`.
- Scenario 02 Intel is validated in workspace `scenario02-intel` with
  `VM.Standard4.Ax.Flex` and unchanged application code.
- Neither completed stack should be mutated until Scenario 03 explicitly
  chooses whether to extend one stack or use another isolated workspace/state.
- The routing behavior requires deliberate application/API changes; it is not
  an unfinished Scenario 02 item.

## Target Topology

```text
Client
  -> orchestrator/Chronos VM
       -> Chronos ML service on 127.0.0.1:8081
       -> AMD vLLM endpoint on :8000/v1
       -> Intel vLLM endpoint on :8000/v1
```

## Expected Change Surface

| Layer | Expected change |
| --- | --- |
| Terraform | Add second private vLLM VM and outputs. |
| vLLM bootstrap | Reuse same CPU cloud-init path for both VMs. |
| Orchestrator config | Add named vLLM endpoint registry. |
| API | Add optional `llm_route`. |
| Response | Add routing metadata. |
| Chronos ML service | No change. |

## Proposed Routing Values

| Value | Meaning |
| --- | --- |
| `default` | Use configured default endpoint. |
| `amd` | Prefer AMD endpoint. |
| `intel` | Prefer Intel endpoint. |
| `auto` | Choose by simple health/availability policy. |
| `shadow` | Return primary output and call alternate endpoint for telemetry. |

## Proposed Config

```text
VLLM_DEFAULT_ENDPOINT=amd
VLLM_AMD_BASE_URL=http://10.0.1.98:8000/v1
VLLM_AMD_MODEL=Qwen/Qwen3-0.6B
VLLM_AMD_API_KEY=<redacted>
VLLM_INTEL_BASE_URL=http://10.0.1.99:8000/v1
VLLM_INTEL_MODEL=Qwen/Qwen3-0.6B
VLLM_INTEL_API_KEY=<redacted>
```

## Validation Commands

From the orchestrator VM:

```bash
curl -fsS http://<amd-private-ip>:8000/v1/models \
  -H "Authorization: Bearer <redacted-key>" | python3 -m json.tool

curl -fsS http://<intel-private-ip>:8000/v1/models \
  -H "Authorization: Bearer <redacted-key>" | python3 -m json.tool
```

Route-specific orchestrator calls:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "scenario-03-amd-route",
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "llm_route": "amd"
  }' | python3 -m json.tool

curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "scenario-03-intel-route",
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "llm_route": "intel"
  }' | python3 -m json.tool
```

## Results

Pending.

## Known Gaps

- Requires code changes to make the vLLM client route-aware.
- Requires Terraform changes to create the second private vLLM VM.
- Requires response metadata design for routing attempts.
