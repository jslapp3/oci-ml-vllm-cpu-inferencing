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
- Scenario 03 will use a new isolated Terraform workspace/state:
  `scenario03-dual-routing`.
- Neither completed stack should be mutated for Scenario 03.
- The routing behavior requires deliberate application/API changes; it is not
  an unfinished Scenario 02 item.

## State Strategy

Use a fresh Scenario 03 stack rather than extending Scenario 01 or Scenario 02.
This preserves both completed proofs as evidence and makes the dual-routing
experiment stand on its own.

| Scenario | Workspace | Purpose |
| --- | --- | --- |
| Scenario 01 | `default` | AMD baseline evidence. |
| Scenario 02 | `scenario02-intel` | Intel recreation evidence. |
| Scenario 03 | `scenario03-dual-routing` | One orchestrator with AMD and Intel vLLM endpoints. |

The Scenario 03 plan should create a complete stack in its own state. It should
not import, mutate, or destroy the Scenario 01 or Scenario 02 resources.

## Target Topology

```text
Client
  -> orchestrator/Chronos VM
       -> Chronos ML service on 127.0.0.1:8081
       -> AMD vLLM endpoint on :8000/v1
       -> Intel vLLM endpoint on :8000/v1
```

Recommended private addresses inside the Scenario 03 VCN:

| Host | Shape | Private IP |
| --- | --- | --- |
| Orchestrator/Chronos | `VM.Standard.E6.Ax.Flex` | `10.0.0.71` |
| AMD vLLM | `VM.Standard.E6.Ax.Flex` | `10.0.1.98` |
| Intel vLLM | `VM.Standard4.Ax.Flex` | `10.0.1.99` |

## Expected Change Surface

| Layer | Expected change |
| --- | --- |
| Terraform | Add second private vLLM VM and outputs. |
| vLLM bootstrap | Reuse same CPU cloud-init path for both VMs. |
| Orchestrator config | Add named vLLM endpoint registry. |
| API | Add optional `llm_route`. |
| Response | Add routing metadata. |
| Chronos ML service | No change. |

## Implementation Plan

1. Terraform:
   - create a non-secret `scenario03-dual-routing.tfvars.example` overlay;
   - add explicit AMD and Intel private vLLM instances in the Scenario 03
     stack;
   - reuse the same `cloud-init/vllm-cpu.yaml.tftpl` for both vLLM hosts;
   - expose AMD and Intel private IP outputs;
   - keep public TCP/8080 closed by default.
2. Configuration:
   - preserve current single-endpoint `VLLM_BASE_URL`, `VLLM_MODEL`, and
     `VLLM_API_KEY` compatibility;
   - add named AMD/Intel endpoint settings;
   - set `VLLM_DEFAULT_ENDPOINT=amd` initially.
3. API:
   - add optional `llm_route` to JSON `/predict`;
   - add optional `llm_route` to CSV `/predict/csv`;
   - ensure the ML service payload excludes `llm_route`.
4. vLLM client:
   - add an endpoint registry;
   - route feature extraction, explanation, and recommendations consistently;
   - try the selected endpoint first and the alternate endpoint on failure;
   - preserve template fallback if both endpoints fail.
5. Response:
   - add `llm_routing` metadata without API keys;
   - include requested route, selected endpoint, fallback status, and attempt
     details.

## Proposed Routing Values

| Value | Meaning |
| --- | --- |
| `default` | Use configured default endpoint. |
| `amd` | Prefer AMD endpoint. |
| `intel` | Prefer Intel endpoint. |
| `auto` | Choose by simple health/availability policy. |
| `shadow` | Return primary output and call alternate endpoint for telemetry. |

Initial implementation should support `default`, `amd`, and `intel` first.
`auto` and `shadow` remain planned follow-ups after explicit route validation
passes.

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

Backward compatibility rule: if named AMD settings are absent, the client
should treat the existing single-endpoint `VLLM_BASE_URL`, `VLLM_MODEL`, and
`VLLM_API_KEY` values as the default/AMD endpoint.

## Proposed Response Metadata

```json
{
  "llm_routing": {
    "requested_route": "intel",
    "selected_endpoint": "intel",
    "fallback_used": false,
    "attempts": [
      {
        "endpoint": "intel",
        "task": "explanation",
        "available": true,
        "latency_ms": 842,
        "error": null
      }
    ]
  }
}
```

Do not include base API keys, raw secrets, or unredacted environment values in
this metadata.

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
- Requires response metadata implementation for routing attempts.
- Requires a Scenario 03 isolated Terraform plan before any apply.
