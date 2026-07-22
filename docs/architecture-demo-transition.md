# Architecture Demo Transition Guide

This project is moving from a single working MVP into an architecture demo that proves three related ideas:

1. the current AMD vLLM + Chronos deployment is reproducible from Terraform;
2. the vLLM inferencing VM can migrate from AMD to Intel with minimal application change;
3. a single deployment can route vLLM language inference between AMD and Intel endpoints.

The important discipline: keep one app codebase and prove these as deployment scenarios, not as diverging project versions.

The OCI compartment labels `v1-cpu-inferencing` and `v2-cpu-inferencing`
identify environments, not application versions or code forks. v1 is the
working control; v2 is the Terraform-managed scenario environment that evolves
through scenarios 01–03.

## What The Repo Already Tells Us

These facts are discoverable from code, docs, Terraform, and example config.

| Area | Repo-derived fact |
| --- | --- |
| Public API | Orchestrator listens on `ORCHESTRATOR_PORT=8080`. |
| Chronos service | ML service listens on `ML_SERVICE_PORT=8081`, bound to localhost in systemd. |
| vLLM service | Private vLLM endpoint exposes OpenAI-compatible API on `:8000/v1`. |
| vLLM role | vLLM generates explanation, recommendations, and optional note-derived features; it does not generate numeric forecasts. |
| Numeric model | Current Chronos model is `autogluon/chronos-2-small`, revision `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a`. |
| Rollback model | Original Chronos rollback is `amazon/chronos-t5-small`. |
| vLLM default model | Local examples use `meta-llama/Llama-3.1-8B-Instruct`; Terraform example uses `Qwen/Qwen3-0.6B`. |
| Runtime style | No containers; Python virtual environments plus `systemd`. |
| App install path | `/opt/oci-vllm-ml-inference`. |
| App env path | `/etc/oci-forecast/forecast.env`. |
| vLLM env path | `/etc/vllm/vllm.env`. |
| Systemd services | `chronos-ml.service`, `forecast-orchestrator.service`, `vllm-openai.service`. |
| Terraform baseline | One public orchestrator/Chronos VM and one private vLLM VM. |
| Terraform default VCN | `10.0.0.0/16`. |
| Terraform public subnet | `10.0.0.0/24`. |
| Terraform private subnet | `10.0.1.0/24`. |
| Terraform orchestrator private IP | `10.0.0.71`. |
| Terraform vLLM private IP | `10.0.1.98`. |
| Terraform default shapes | `VM.Standard.E6.Ax.Flex` for both orchestrator and vLLM. |
| Terraform status | Scenario 01 has passed a fresh v2 AMD baseline apply and smoke validation. |

## What Was Captured From OCI

These values were captured read-only for the working v1 control and redacted in
the scenario record. Do not paste raw secrets, private keys, Terraform state, or
unredacted environment files into the repository.

| Area | Captured status |
| --- | --- |
| Existing deployment identity | Region, compartment, AD, VCN, subnet, route, gateway, and network-control details captured. |
| Existing instances | Display names, shapes, OCPUs, memory, image/OS, and boot volumes captured; OCIDs kept out of tracked docs. |
| Existing IPs | Private IPs captured; public IP details kept out of tracked docs where not required. |
| Existing runtime | Python, vLLM, uv, Torch, and Chronos package versions captured. |
| Existing service health | Current `systemctl status` and health checks captured for all three services. |
| Existing service logs | Recent filtered journal snippets reviewed without committing sensitive raw logs. |
| Existing config | Redacted `/etc/oci-forecast/forecast.env` and `/etc/vllm/vllm.env` reviewed. |
| Existing smoke output | `/health`, `/v1/models`, and `/predict` passed with secrets removed. |
| AMD Terraform baseline | v2 clean apply, instance rotation, service gates, smoke test, public TCP/8080 denial, and drift check passed. |
| Intel capacity | Still pending for `VM.Standard4.Ax.Flex`. |

The remaining OCI capture before scenario 02 is Intel-specific: quota/capacity,
shape-change behavior, and whether private IP preservation works for the
selected migration path.

## Scenario Structure

Use one codebase and three scenario records:

| Scenario | Purpose | Validation target |
| --- | --- | --- |
| `01-amd-baseline` | Prove current Terraform baseline works cleanly. | Fresh AMD vLLM + Chronos deployment from Terraform. |
| `02-amd-to-intel-migration` | Prove shape migration from AMD to Intel. | Same vLLM service contract after migration. |
| `03-dual-vllm-routing` | Prove routing between AMD and Intel vLLM endpoints. | `llm_route` or equivalent routing policy selects endpoint. |

## Milestone Order

### Milestone 1 — Validate AMD Terraform Baseline

This control case is complete for the architecture demo.

Success means:

- Terraform formatted, validated, planned, and applied in the isolated v2 environment.
- Cloud-init completed on both VMs.
- `chronos-ml.service`, `forecast-orchestrator.service`, and `vllm-openai.service` started.
- vLLM `/v1/models` worked from the orchestrator network path.
- Orchestrator `/health` worked.
- `/predict` smoke returned Chronos-2 output and non-fallback Qwen text.
- Public TCP/8080 stayed closed.
- Final Terraform drift check passed.

### Milestone 2 — Prove AMD-To-Intel vLLM Migration

Change the vLLM VM shape path from AMD to Intel, preferably to `VM.Standard4.Ax.Flex`.

Success means:

- No application code change is needed.
- vLLM still exposes the same OpenAI-compatible API.
- The orchestrator can keep using the same `VLLM_BASE_URL` if the private IP is preserved.
- Any required Terraform or OCI shape-change behavior is documented.

### Milestone 3 — Prove Dual vLLM Routing

Add a second private vLLM endpoint and route language-generation calls between AMD and Intel.

Success means:

- Both endpoints run the same vLLM model.
- The orchestrator can select AMD or Intel.
- Existing requests continue to work without a routing parameter.
- Routing metadata is visible without exposing secrets.

## Immediate Next Step

Scenario 01 evidence is recorded. The next architecture-demo step is Scenario
02 against the v2 environment:

1. confirm `VM.Standard4.Ax.Flex` quota and capacity in `us-ashburn-1`;
2. plan the vLLM shape migration and determine whether OCI/Terraform performs
   an in-place update or replacement;
3. preserve the vLLM private IP where possible so `VLLM_BASE_URL` remains
   stable; and
4. rerun the service and `/predict` smoke gates after migration.

Keep the v1 control deployment intact while v2 evolves through scenarios 02 and
03.
