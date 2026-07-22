# Second vLLM VM and Routing Architecture Plan

## Summary

Create a fresh Scenario 03 Terraform stack with one private-subnet AMD vLLM VM
and one private-subnet Intel vLLM VM. Treat both as equivalent
OpenAI-compatible endpoints running the same model, then update the
orchestrator to route language-generation calls through an endpoint registry.
Do not mutate the completed Scenario 01 AMD or Scenario 02 Intel stacks.

The recommended v1 implementation is intentionally low-risk: do not introduce a separate router service yet. Put routing in the orchestrator, expose an optional request parameter, support fallback to the other endpoint, and record routing metadata in responses.

Current architecture:

```text
Client
  -> forecast orchestrator :8080
       -> Chronos ML service 127.0.0.1:8081
       -> AMD vLLM private endpoint :8000/v1
       -> Oracle Autonomous Database, optional
```

For Scenario 03, "current" means the new isolated stack before route-aware app
changes are validated, not the completed Scenario 01 or Scenario 02 states.

Target architecture:

```text
Client
  -> forecast orchestrator :8080
       -> Chronos ML service 127.0.0.1:8081
       -> vLLM endpoint registry / routing logic
            -> AMD vLLM private endpoint :8000/v1
            -> Intel vLLM private endpoint :8000/v1
       -> Oracle Autonomous Database, optional
```

OCI shape reference:

- Existing AMD default: `VM.Standard.E6.Ax.Flex`
- Proposed Intel default: `VM.Standard4.Ax.Flex`
- Alternative Intel flexible shape: `VM.Standard3.Flex`
- Oracle Compute shape docs: <https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm>

## Architecture Options

### Option A — Orchestrator-level routing, recommended v1

- Add AMD and Intel vLLM endpoints to orchestrator config.
- API request can specify `llm_route`.
- Orchestrator selects the endpoint before calling vLLM.
- Lowest operational complexity.
- No additional internal service to deploy, secure, or monitor.

This is the best fit for the current MVP because the existing orchestrator already owns vLLM calls for feature extraction, explanation, and recommendations.

### Option B — Dedicated model-router service

- Add a small internal service between the orchestrator and the vLLM VMs.
- Orchestrator calls one router URL.
- Router handles endpoint selection, retries, health checks, metrics, and routing policy.

This is cleaner if multiple applications will share the same vLLM pool, but it adds deployment and operational overhead that is not necessary for a first dual-VM experiment.

### Option C — Infrastructure/load-balancer routing

- Put both vLLM VMs behind a private load balancer.
- Useful for round-robin, weighted, or health-based routing.
- Weak fit for caller-selected chip routing unless separate backend sets or listeners are exposed.

This is reasonable for availability once both endpoints are equivalent, but it is less useful when the goal is to explicitly test AMD versus Intel behavior.

### Option D — Semantic or policy routing

- Route based on prompt length, notes content, task type, latency budget, endpoint health, or policy rules.
- Useful later if there are measurable differences between chip families or model-serving configurations.
- Requires explicit rules and more tests.

This should build on the same endpoint registry introduced by Option A.

### Option E — Shadow/compare routing

- Return the production response from one endpoint.
- Also call the other endpoint for migration telemetry.
- Record status and latency, but do not make the secondary result authoritative.

This is useful for simulating migration from AMD to Intel. It should be opt-in because it doubles vLLM generation work.

## Recommended v1 Design

Use orchestrator-level routing with a named endpoint registry.

Use Terraform workspace `scenario03-dual-routing` for the first dual-endpoint
deployment. Preserve `default` and `scenario02-intel` as completed evidence
stacks.

### Endpoint names

Use stable route names:

- `amd`
- `intel`
- `default`
- `auto`
- `shadow`

`default` resolves to the configured `VLLM_DEFAULT_ENDPOINT`, initially `amd` to preserve current behavior.

### Request interface

Add optional `llm_route` to JSON `POST /predict`:

```json
{
  "series_id": "demand-demo",
  "values": [120, 127, 131, 138],
  "prediction_length": 2,
  "notes": "Promotion ends after the first forecast day.",
  "llm_route": "intel"
}
```

Add optional `llm_route` form field to CSV `POST /predict/csv`:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict/csv \
  -F "file=@examples/chronos2_covariate_test.csv;type=text/csv" \
  -F "date_column=date" \
  -F "target_column=demand" \
  -F "prediction_length=3" \
  -F "llm_route=intel"
```

Supported values:

| Value | Behavior |
| --- | --- |
| `default` | Use `VLLM_DEFAULT_ENDPOINT`. |
| `amd` | Prefer AMD endpoint first. |
| `intel` | Prefer Intel endpoint first. |
| `auto` | Use simple health/availability policy. Start with default if healthy, otherwise alternate. |
| `shadow` | Return primary endpoint output and also call alternate endpoint for telemetry. |

Invalid route values should return HTTP `400`.

Initial implementation can ship `default`, `amd`, and `intel` first. Keep
`auto` and `shadow` documented but deferred until explicit AMD/Intel route
validation passes.

### Response interface

Keep existing response fields:

- `explanation`
- `recommendations`
- `extracted_features`
- `warnings`

Add `llm_routing`:

```json
{
  "llm_routing": {
    "requested_route": "intel",
    "selected_endpoint": "intel",
    "fallback_used": false,
    "attempts": [
      {
        "endpoint": "intel",
        "base_url": "http://10.0.1.99:8000/v1",
        "task": "explanation",
        "available": true,
        "latency_ms": 842,
        "error": null
      }
    ]
  }
}
```

Do not expose API keys in response metadata.

### Failure behavior

- If selected endpoint succeeds, use it.
- If selected endpoint fails, try the other configured endpoint.
- If both fail, preserve the existing deterministic template fallback behavior.
- Add a warning when cross-endpoint fallback is used.
- Preserve current single-endpoint behavior if only one vLLM endpoint is configured.

## Code Changes

### Orchestrator schema and request handling

Add `llm_route` to `PredictionRequest`.

For CSV requests, add `llm_route` as a form field and pass it into the generated `PredictionRequest`.

The ML forecast payload must continue to exclude LLM-only fields. Today `_ml_payload()` removes `notes`; it should also remove `llm_route`.

### vLLM settings

Current code assumes one endpoint:

```text
VLLM_BASE_URL
VLLM_MODEL
VLLM_API_KEY
VLLM_TIMEOUT_SECONDS
VLLM_TEMPERATURE
VLLM_MAX_TOKENS
```

Add named endpoint config while preserving current variables as backward-compatible defaults:

```text
VLLM_DEFAULT_ENDPOINT=amd

VLLM_AMD_BASE_URL=http://10.0.1.98:8000/v1
VLLM_AMD_MODEL=Qwen/Qwen3-0.6B
VLLM_AMD_API_KEY=<shared-or-amd-key>

VLLM_INTEL_BASE_URL=http://10.0.1.99:8000/v1
VLLM_INTEL_MODEL=Qwen/Qwen3-0.6B
VLLM_INTEL_API_KEY=<shared-or-intel-key>

VLLM_TIMEOUT_SECONDS=10
VLLM_TEMPERATURE=0.2
VLLM_MAX_TOKENS=500
```

Compatibility rule:

- If `VLLM_AMD_BASE_URL` is unset, use existing `VLLM_BASE_URL`.
- If `VLLM_AMD_MODEL` is unset, use existing `VLLM_MODEL`.
- If `VLLM_AMD_API_KEY` is unset, use existing `VLLM_API_KEY`.

### vLLM client

Refactor `VLLMCompanionClient` around an endpoint registry.

Recommended internal concepts:

- `LLMEndpoint`
  - `name`
  - `base_url`
  - `model_name`
  - `api_key`
- `LLMRouteDecision`
  - requested route
  - selected endpoint
  - fallback endpoint order
- `LLMAttempt`
  - endpoint
  - task
  - available
  - latency
  - error

The client should accept a route context on:

- `extract_structured_features(...)`
- `generate_explanation(...)`
- `generate_recommendations(...)`

Centralize endpoint attempt logic so all three tasks share the same routing and fallback behavior.

### Orchestrator response assembly

`_run_prediction()` currently calls vLLM three times:

```python
extracted_features = await app.state.llm_client.extract_structured_features(request.notes)
explanation = await app.state.llm_client.generate_explanation(ml_output, request.notes)
recommendations = await app.state.llm_client.generate_recommendations(ml_output, request.notes)
```

Update this flow so the same route policy applies consistently across all LLM tasks.

Recommended v1 behavior:

- Use the same selected primary endpoint for explanation and recommendations.
- Feature extraction may use the same endpoint for consistency.
- If a task fails on the selected endpoint, fallback to the alternate endpoint for that task.
- Append all attempt metadata into `llm_routing`.

## Terraform Changes

### Current infrastructure shape

Current Terraform provisions:

- one public orchestrator/Chronos VM
- one private vLLM VM
- one public subnet
- one private subnet
- one vLLM NSG
- one vLLM cloud-init template

### Target infrastructure shape

Provision:

- one public orchestrator/Chronos VM
- one private AMD vLLM VM
- one private Intel vLLM VM
- same private subnet
- same or separate vLLM NSGs
- same vLLM cloud-init template, parameterized for each VM

### Variables

Keep existing variables for backward compatibility where practical, but rename or alias conceptually:

```hcl
vllm_amd_shape       = "VM.Standard.E6.Ax.Flex"
vllm_amd_ocpus       = 16
vllm_amd_memory_gbs  = 128
vllm_amd_private_ip  = "10.0.1.98"

vllm_intel_shape      = "VM.Standard4.Ax.Flex"
vllm_intel_ocpus      = 16
vllm_intel_memory_gbs = 128
vllm_intel_private_ip = "10.0.1.99"

vllm_model   = "Qwen/Qwen3-0.6B"
vllm_api_key = "<random-long-token>"
```

If separate keys are desired:

```hcl
vllm_amd_api_key   = null
vllm_intel_api_key = null
```

Default behavior should use shared `vllm_api_key`.

### Compute resources

Refactor existing `oci_core_instance.vllm` into either:

- two explicit resources: `vllm_amd` and `vllm_intel`; or
- one `for_each` resource keyed by endpoint name.

Explicit resources are clearer for this MVP. `for_each` is cleaner if more endpoint types are expected.

Recommended v1: explicit resources.

### Cloud-init

Reuse `cloud-init/vllm-cpu.yaml.tftpl` for both AMD and Intel.

Parameterize:

- endpoint label
- model name
- API key
- Hugging Face token
- KV cache size
- orchestrator private CIDR

Both endpoints should run:

```text
vllm serve ${VLLM_MODEL} --host 0.0.0.0 --port 8000 --api-key ${VLLM_API_KEY} --dtype bfloat16
```

If `bfloat16` proves problematic on a chosen Intel CPU shape, make dtype configurable:

```hcl
vllm_dtype = "bfloat16"
```

### Network/security

Allow orchestrator private IP to reach both vLLM VMs:

- TCP `8000` for OpenAI-compatible API
- TCP `22` for SSH via jump host

Existing vLLM NSG can be reused if both vLLM VMs have the same allowed traffic pattern.

### Outputs

Add outputs:

- `vllm_amd_private_ip`
- `vllm_intel_private_ip`
- `ssh_vllm_amd_via_orchestrator`
- `ssh_vllm_intel_via_orchestrator`

Optionally keep old `vllm_private_ip` output as an alias for AMD during transition.

## Documentation Changes

Update:

- `README.md`
- `docs/architecture.md`
- `docs/runbook.md`
- `docs/chronos-vllm-explainer.md`
- `infra/terraform/README.md`
- `deploy/compute.env.example`
- `.env.example`

Docs should explain:

- Chronos numeric forecasting is unchanged.
- vLLM remains language-only.
- AMD and Intel endpoints run the same model.
- `llm_route` changes the language-generation endpoint only.
- Failover from one chip endpoint to the other does not affect the numeric forecast.
- Shadow mode is for migration telemetry, not model-quality judgment.

## Routing Methods To Support or Document

### Explicit API routing

Caller sends:

```json
{
  "llm_route": "amd"
}
```

or:

```json
{
  "llm_route": "intel"
}
```

Best for benchmarking and chip-specific validation.

### Config default routing

Operator sets:

```text
VLLM_DEFAULT_ENDPOINT=intel
```

Best for migration from AMD to Intel without requiring client changes.

### Failover routing

Try selected/default endpoint first. On timeout, connection error, HTTP error, invalid response, or empty response, try the alternate endpoint.

Best for availability.

### Auto routing

Start simple:

- prefer configured default if it has not recently failed;
- otherwise choose alternate;
- periodically recheck default.

Avoid complex latency ranking until metrics exist.

### Shadow routing

Return primary endpoint output. Also call alternate endpoint and record telemetry.

Best for simulating migration from AMD to Intel.

Do not compare generated text semantically in v1. Record only:

- success/failure
- latency
- error class
- endpoint name
- model name

### Semantic routing

Future option:

- prompt length
- notes content
- task type
- latency budget
- endpoint health
- model/version compatibility

Do not implement semantic routing as the first step unless there is a concrete policy to encode.

## Migration Simulation Effort

### Architecture effort

Low to moderate.

The vLLM server is already isolated on its own VM, so adding Intel is mostly Terraform duplication plus endpoint registry config. The existing private subnet and NSG model already support this pattern.

### Code effort

Moderate.

Current code assumes exactly one vLLM endpoint. The main change is replacing scalar `LLMSettings` with named endpoint settings and route-aware client calls.

Forecasting code does not change because Chronos is separate from vLLM.

### Operational effort

Moderate.

Required checks:

- Validate Intel shape quota/capacity in the OCI region.
- Confirm the same Oracle Linux image works on `VM.Standard4.Ax.Flex`.
- Confirm Python 3.12 and vLLM CPU wheel install correctly.
- Confirm model startup path is valid on Intel.
- Run `/v1/models` and orchestrator smoke tests against both private IPs.

## Test Plan

### Unit tests

- Existing single-endpoint config remains backward-compatible.
- `llm_route=amd` calls AMD endpoint.
- `llm_route=intel` calls Intel endpoint.
- `llm_route=default` resolves to configured default.
- selected endpoint failure falls back to the other endpoint.
- both endpoint failures preserve existing template fallback.
- response includes `llm_routing`.
- response does not expose API keys.
- `_ml_payload()` does not forward `llm_route` to the Chronos ML service.

### API tests

- JSON `/predict` accepts `llm_route`.
- CSV `/predict/csv` accepts `llm_route`.
- invalid route returns `400`.
- existing requests without `llm_route` continue to pass.

### Terraform validation

Run:

```bash
terraform fmt -check -recursive
terraform validate
terraform plan
```

Expected plan:

- one additional private vLLM VM;
- new/updated outputs;
- no replacement of existing AMD VM unless variables are intentionally changed.

### Manual smoke tests

From the orchestrator VM:

```bash
curl -fsS http://<amd-private-ip>:8000/v1/models \
  -H "Authorization: Bearer $VLLM_API_KEY" | python3 -m json.tool

curl -fsS http://<intel-private-ip>:8000/v1/models \
  -H "Authorization: Bearer $VLLM_API_KEY" | python3 -m json.tool
```

Then test orchestrator routing:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "routing-smoke-amd",
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "llm_route": "amd"
  }' | python3 -m json.tool

curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "routing-smoke-intel",
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "llm_route": "intel"
  }' | python3 -m json.tool
```

Expected:

- `ml_output.engine` remains `chronos` or fallback independently of vLLM route.
- `llm_routing.selected_endpoint` matches requested route when that endpoint succeeds.
- explanation/recommendation fallback still works if both vLLM endpoints fail.

## Assumptions

- Existing AMD endpoint remains on `VM.Standard.E6.Ax.Flex`.
- New Intel endpoint targets `VM.Standard4.Ax.Flex`.
- Both endpoints run the same `VLLM_MODEL`.
- Both endpoints can share the same API key unless separate keys are explicitly configured.
- v1 routing should live in orchestrator code, not a new router service.
- Shadow/compare mode is for architecture and migration telemetry, not for comparing generated language quality.
- Chronos numeric forecasting remains unchanged.
