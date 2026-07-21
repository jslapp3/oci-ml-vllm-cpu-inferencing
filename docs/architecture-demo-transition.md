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
| Terraform status | Docs explicitly say the Terraform path is experimental until validated by a fresh end-to-end apply. |

## What We Still Need To Capture From OCI

These cannot be safely inferred from code. They require live OCI inspection or commands run on the existing VMs.

| Area | Needed capture |
| --- | --- |
| Existing deployment identity | Compartment, region, availability domain, VCN, subnets, route tables, gateways, NSGs/security lists. |
| Existing instances | Instance OCIDs, display names, shapes, OCPUs, memory, image/OS version, boot volume size. |
| Existing IPs | Orchestrator public/private IP and vLLM private IP. |
| Existing runtime | Python versions, vLLM version, uv version, Torch version, Chronos package version. |
| Existing service health | Current `systemctl status` for all three services. |
| Existing service logs | Recent journal snippets for Chronos, orchestrator, and vLLM. |
| Existing config | Redacted `/etc/oci-forecast/forecast.env` and `/etc/vllm/vllm.env`. |
| Existing smoke output | `/health`, `/v1/models`, and `/predict` outputs with secrets removed. |
| OCI capacity | Quota and availability for target Intel shape, especially `VM.Standard4.Ax.Flex`. |
| Terraform behavior | Whether the current Terraform plan creates, updates, or replaces resources in a clean compartment. |

Do not paste or commit raw secret values. Capture key names and redacted values only.

## Scenario Structure

Use one codebase and three scenario records:

| Scenario | Purpose | Validation target |
| --- | --- | --- |
| `01-amd-baseline` | Prove current Terraform baseline works cleanly. | Fresh AMD vLLM + Chronos deployment from Terraform. |
| `02-amd-to-intel-migration` | Prove shape migration from AMD to Intel. | Same vLLM service contract after migration. |
| `03-dual-vllm-routing` | Prove routing between AMD and Intel vLLM endpoints. | `llm_route` or equivalent routing policy selects endpoint. |

## Milestone Order

### Milestone 1 — Validate AMD Terraform Baseline

This is the control case. Do not start Intel or routing work until this is done.

Success means:

- Terraform formats, validates, plans, and applies in a disposable environment.
- Cloud-init completes on both VMs.
- `chronos-ml.service`, `forecast-orchestrator.service`, and `vllm-openai.service` start.
- vLLM `/v1/models` works from the orchestrator network path.
- Orchestrator `/health` works.
- `/predict` smoke test works or degrades in an explained way.
- Validation evidence is recorded.

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

The existing manual deployment has been captured and moved into
`cpu-inferencing/v1-cpu-inferencing`. New Terraform work targets the sibling
`cpu-inferencing/v2-cpu-inferencing` compartment. OCI-managed protected DNS
resolver/view resources remain in the parent compartment.

The v2 Terraform plan contains 17 creates, zero changes, and zero destroys.
Review and apply that saved plan, validate cloud-init and all service/smoke
gates, and record the evidence here and in scenario 01.

The existing deployment should remain untouched until the clean baseline is proven.
