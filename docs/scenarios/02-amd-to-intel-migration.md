# Scenario 02: AMD To Intel Recreation

Status: **Passed on 2026-07-22.**

## Intent

Prove that the working AMD architecture can be reproduced on Intel with the
same application code and the same vLLM service contract:

```text
http://<vllm-private-ip>:8000/v1
```

This scenario is intentionally not a lift-and-shift of the existing vLLM VM.
The primary test is a clean Intel recreation using the same Terraform stack
code with different inputs. The point is to determine whether the CPU family can
change with zero app-code changes and only expected infrastructure/configuration
changes.

Keep Scenario 01's AMD v2 stack available as the control while this Intel stack
is created and validated. After clean Intel recreation succeeds, an optional
secondary test may change only `vllm_shape` in an existing AMD stack to observe
OCI/Terraform shape-swap behavior.

## Expected Change Surface

| Layer | Expected change |
| --- | --- |
| App code | None. |
| Orchestrator config | Only endpoint/config values such as `VLLM_BASE_URL`, if the recreated Intel stack uses a different private IP. |
| vLLM systemd command | Prefer none; use the same CPU vLLM service contract. |
| vLLM cloud-init | Prefer none; reuse the AMD baseline's CPU vLLM bootstrap path. |
| Terraform code | Prefer none beyond fixes that remove hidden AMD coupling. |
| Terraform inputs/state | New Scenario 02 Intel stack/state with Intel shape and placement inputs. |
| OCI runtime | Instance shape, CPU flags, performance characteristics. |

## Terraform Strategy

Use the same Terraform module/code, but create a separate Scenario 02 Intel
stack/state first. This gives a clean architecture proof without destroying or
mutating the known-good AMD Scenario 01 baseline.

Recommended first pass:

```hcl
project_name = "oci-vllm-ml-inference-s02-intel"
vllm_shape   = "VM.Standard4.Ax.Flex"
```

The tracked
[`scenario02-intel.tfvars.example`](../../infra/terraform/scenario02-intel.tfvars.example)
provides these non-secret differences as an overlay. Keep credentials, OCIDs,
availability-domain placement, SSH/admin inputs, app repo/ref, and tokens in
ignored private inputs.

The deployed stack uses the dedicated `scenario02-intel` Terraform workspace.
Select and verify it before future plans. Do not use the Scenario 02 overlay
from the Scenario 01 workspace:

```bash
cd infra/terraform
terraform workspace select scenario02-intel
terraform workspace show
terraform plan -var-file=scenario02-intel.tfvars.example
```

The workspace check must print `scenario02-intel`. Load the existing Scenario
02 key from the local keychain as documented in the Terraform README before a
drift plan; always review future plans before apply.

Use the same app repo/ref, Qwen model, vLLM bootstrap template, and validation
gates as Scenario 01. If the Intel stack uses a separate VCN, the same fixed
private IPs may be reused. If it shares a VCN or otherwise needs different
addresses, treat `VLLM_BASE_URL` as an infrastructure/configuration change, not
an application-code change.

Terraform now performs independent Oracle Linux image lookups: the orchestrator
lookup is keyed to `var.orchestrator_shape`, and the vLLM lookup is keyed to
`var.vllm_shape`. Optional `orchestrator_image_id` and `vllm_image_id` values
can override either lookup. The backward-compatible shared `image_id` remains
available but should be used only when one image is compatible with both
shapes.

## Target Intel Shape

Default target:

```hcl
vllm_shape = "VM.Standard4.Ax.Flex"
```

If the Intel stack has its own VCN, these fixed private IPs may remain the same
as Scenario 01 without conflict:

```hcl
orchestrator_private_ip = "10.0.0.71"
vllm_private_ip = "10.0.1.98"
```

If `VM.Standard4.Ax.Flex` capacity is unavailable in the initial availability
domain, try another availability domain before changing the target shape. If all
preferred Intel placement fails, record the capacity result and decide whether
to request capacity/quota or test an alternate Intel flexible shape such as
`VM.Standard3.Flex`.

## Recreation Validation

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
    "series_id": "scenario-02-intel-recreation",
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "notes": "Intel vLLM migration validation."
  }' | python3 -m json.tool
```

## Results

### 2026-07-22 Terraform Preparation And Review-Only Plan

- Created and selected a dedicated, empty `scenario02-intel` Terraform
  workspace. The Scenario 01 AMD baseline remains in the separate `default`
  workspace.
- Terraform formatting and validation passed using the locally installed OCI
  provider.
- A Scenario 02 review-only plan completed with 17 creates, zero changes, and
  zero destroys. It plans a complete Scenario 02 network and two-VM stack; it
  does not mutate Scenario 01 resources.
- The plan keeps the orchestrator on `VM.Standard.E6.Ax.Flex` and selects
  `VM.Standard4.Ax.Flex` for the private vLLM host.
- Both shape-specific Oracle Linux image lookups resolved, Scenario 02 resource
  names use the `oci-vllm-ml-inference-s02-intel` prefix, and no public API
  ingress rule is planned.
- The local workflow supplies `vllm_api_key` through process environment. Since
  no real Scenario 02 key was provided for this review, the plan used an
  explicit non-secret placeholder and must not be applied. Produce a new plan
  with a real per-environment key before any apply.
- No Terraform apply was run.

At this review-only stage, the Limits and capacity-report APIs could not be
queried because they require the tenancy root OCID and local credential files
were intentionally not inspected. The subsequent deployment tested capacity
directly and succeeded in the configured AD.

### 2026-07-22 Intel Recreation Deployment

- Generated a fresh Scenario 02 vLLM API key in process memory, created an
  applyable plan, and applied it from the isolated `scenario02-intel`
  workspace. Terraform created 17 resources with zero changes and zero
  destroys.
- The configured availability domain had capacity for
  `VM.Standard4.Ax.Flex` on the first attempt, so no cross-AD retry was needed.
- The Scenario 01 AMD baseline in the `default` workspace was not planned,
  changed, or destroyed.
- Cloud-init completed successfully on both hosts. `chronos-ml.service`,
  `forecast-orchestrator.service`, and `vllm-openai.service` are active.
- The vLLM host reports `GenuineIntel` and an Intel Xeon processor. The vLLM
  service command line does not contain `--api-key`.
- Chronos and orchestrator health checks passed. Chronos-2 preloaded the pinned
  `autogluon/chronos-2-small` model successfully.
- Authenticated private `/v1/models` returned `Qwen/Qwen3-0.6B`.
- The Scenario 02 `/predict` smoke completed with a two-step Chronos-2 forecast,
  no warnings, and non-fallback Qwen explanation and recommendations.
- Public TCP/8080 remained unreachable as intended.
- A final drift plan completed with no changes.
- The generated API key is stored in the local macOS login keychain under the
  service `oci-vllm-ml-inference-scenario02-vllm-api-key`; its value was not
  printed or written to a tracked file.

## Known Gaps

- Optional after clean recreation: test whether changing only `vllm_shape` in
  an existing AMD stack produces an in-place update or replacement. This is a
  follow-on experiment and not a Scenario 02 completion gate.
