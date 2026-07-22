# Scenario 01: AMD Baseline

## Intent

Prove the existing Terraform architecture can recreate the current two-VM MVP:

```text
Client
  -> public orchestrator/Chronos VM
       -> Chronos ML service on 127.0.0.1:8081
       -> private AMD vLLM VM on :8000/v1
```

This is the control scenario for later Intel migration and dual-routing work.

## Repo-Derived Defaults

| Setting | Value |
| --- | --- |
| Orchestrator port | `8080` |
| Chronos ML port | `8081` |
| vLLM API port | `8000` |
| Orchestrator shape | `VM.Standard.E6.Ax.Flex` |
| Orchestrator OCPUs / memory / boot volume | 2 / 16 GB / 100 GB |
| vLLM shape | `VM.Standard.E6.Ax.Flex` |
| vLLM OCPUs / memory / boot volume | 16 / 128 GB / 200 GB |
| Orchestrator private IP | `10.0.0.71` |
| vLLM private IP | `10.0.1.98` |
| VCN CIDR | `10.0.0.0/16` |
| Public subnet CIDR | `10.0.0.0/24` |
| Private subnet CIDR | `10.0.1.0/24` |
| Terraform status | Fresh v2 apply and smoke validation passed. |

## Inputs To Capture

Record these before applying:

- region;
- compartment OCID;
- availability domain;
- SSH public key path;
- admin CIDR blocks;
- public API CIDR blocks;
- app repo URL;
- app repo ref;
- vLLM model;
- redacted vLLM API key indicator, not the key itself.

## Existing Deployment Control Capture

Captured read-only on 2026-07-21. This records the working manually deployed
control. Fresh Terraform baseline evidence is recorded in the results section
below.

### OCI Inventory

| Setting | Captured value |
| --- | --- |
| Region | `us-ashburn-1` |
| Compartment | `cpu-inferencing/v1-cpu-inferencing` (OCID captured out of repo) |
| Availability domain | `PHWx:US-ASHBURN-AD-1` |
| VCN | `inferencing-vcn`, `10.0.0.0/16` (OCID captured out of repo) |
| Public subnet | `10.0.0.0/24`; public IPs allowed; internet-gateway default route |
| Private subnet | `10.0.1.0/24`; public IPs prohibited; NAT-gateway default route; OCI service-gateway route |
| Network controls | Security lists are attached; no NSGs are attached to either VNIC |
| Orchestrator instance | `ml-instance`; instance OCID and public IP captured out of repo |
| Orchestrator compute | `VM.Standard.E6.Ax.Flex`, 2 OCPUs, 16 GB memory, 100 GB boot volume |
| Orchestrator private IP | `10.0.0.71` |
| vLLM instance | `vllm-instance`; instance OCID captured out of repo; no public IP |
| vLLM compute | `VM.Standard.E6.Ax.Flex`, 16 OCPUs, 128 GB memory, 200 GB boot volume |
| vLLM private IP | `10.0.1.98` |
| Image | `Oracle-Linux-9.7-2026.06.15-1`; both hosts currently report Oracle Linux 9.8 |
| Existing ingress | Public SSH is currently broader than the Terraform target; TCP/8080 is limited to two `/32` sources; private TCP/8000 is allowed from `10.0.0.71/32` |

The Terraform defaults now match the captured control sizing for both VMs.

On 2026-07-21 the working control resources were moved from the parent
`cpu-inferencing` compartment into its `v1-cpu-inferencing` child. The VCN,
subnets, gateways, route tables, security lists, DHCP options, VNICs, IPs,
instances, and boot volumes all retained their existing OCIDs and network
configuration. OCI-managed DNS resolver and DNS view resources remain in the
parent because OCI marks them as protected and does not permit moving them.

### Runtime And Configuration

| Host | Captured runtime |
| --- | --- |
| Orchestrator | Python 3.11.13; `chronos-forecasting==2.3.1`; Torch 2.13.0 |
| vLLM | Python 3.12.13 in `/opt/vllm/.venv`; `vllm==0.24.0+cpu`; `uv==0.11.28`; Torch 2.11.0+cpu |

The redacted environment capture confirms:

- Chronos uses `autogluon/chronos-2-small` at revision
  `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a`, CPU, preload enabled, and a
  maximum horizon of 96.
- The orchestrator uses `http://10.0.1.98:8000/v1` and
  `Qwen/Qwen3-0.6B` with a configured API key whose value was not captured.
- The vLLM host uses the same model, a configured API key whose value was not
  captured, 16 GiB of CPU KV cache, and one reserved CPU.
- Database writes are disabled and Oracle credential values are unset.

### Control Health Evidence

At capture time:

- `chronos-ml.service`, `forecast-orchestrator.service`, and
  `vllm-openai.service` were active/running with zero recorded restarts;
- filtered recent journals showed successful service startup and HTTP 200
  responses for health, prediction, model-list, and chat-completion requests;
- Chronos `/health` reported successful preload, a loaded public model, and no
  load error;
- orchestrator `/health` returned `status=ok` and `db_enabled=false`;
- authenticated vLLM `/v1/models` returned `Qwen/Qwen3-0.6B`; and
- the scenario smoke payload completed with Chronos-2, no warnings, no model
  fallback, and non-fallback Qwen explanation/recommendation output.

The same health and smoke gates passed after the compartment move, including a
post-move `/predict` request with Chronos-2 loaded, no warnings, and non-fallback
`Qwen/Qwen3-0.6B` output.

At capture time, the v1 live application checkout was commit
`876a324955ebc2e29e55346e6913258be237c8ba`. The v2 clean Terraform validation
used the reviewed, pushed commit selected below.

## Clean Baseline Input Candidates

These are candidates for the disposable Terraform run, not final approval to
apply:

| Input | Candidate |
| --- | --- |
| Region | `us-ashburn-1` |
| Availability domain | `PHWx:US-ASHBURN-AD-1` |
| SSH public key | Existing `id_ed25519.pub` key verified against the control VM; record only its local path in uncommitted tfvars |
| Admin CIDRs | Current operator public IP as one `/32`; do not copy the control environment's broad SSH rule |
| Public API CIDRs | Current operator public IP as one `/32`, or `[]` when validating only through an SSH tunnel |
| App repo URL | `https://github.com/jslapp3/oci-ml-vllm-cpu-inferencing.git` |
| App repo ref | `ebbe12fda862ff31c8a7abd5490978a9684fa28d` (tested bootstrap-hardening checkpoint on `origin/main`) |
| vLLM model | `Qwen/Qwen3-0.6B` |
| Orchestrator Python | `3.11` package stream; installer fails rather than falling back to Python 3.9 |
| vLLM Python / uv / vLLM | `3.12.13` / `0.11.28` / `0.24.0` CPU wheel |
| vLLM API key | Generate a new per-environment value; store only in ignored local inputs and capture only `[set; redacted]` |
| Target compartment/VCN | `cpu-inferencing/v2-cpu-inferencing`; new isolated Terraform-managed VCN |

## Validation Commands

From `infra/terraform`:

```bash
terraform fmt -check -recursive
terraform validate
terraform plan
```

After apply, from the orchestrator VM:

```bash
sudo cloud-init status --wait
sudo systemctl --no-pager --full status chronos-ml.service
sudo systemctl --no-pager --full status forecast-orchestrator.service
curl -fsS http://127.0.0.1:8081/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8080/health | python3 -m json.tool
```

From the orchestrator VM to the private vLLM VM:

```bash
curl -fsS http://<vllm-private-ip>:8000/v1/models \
  -H "Authorization: Bearer <redacted-key>" | python3 -m json.tool
```

Smoke test through the orchestrator:

```bash
curl -fsS -X POST http://127.0.0.1:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "scenario-01-amd-baseline",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 2,
    "notes": "Baseline AMD vLLM scenario validation."
  }' | python3 -m json.tool
```

## Results

Scenario 01 passed on 2026-07-21 in the isolated
`cpu-inferencing/v2-cpu-inferencing` environment.

Terraform initialization, formatting, validation, and planning passed. The v2
plan contained 17 creates, zero changes, and zero destroys, and targeted only
the v2 compartment. The plan was applied successfully.

An initial post-apply SSH check failed because the operator public egress IP had
changed. The ignored local `terraform.tfvars` admin CIDR was updated, and
Terraform applied a scoped NSG-only change: one SSH rule was added and one stale
SSH rule was removed.

During validation, `vllm-openai.service` was found to expose the vLLM API key in
process arguments through `--api-key`. The cloud-init template now relies on
`VLLM_API_KEY` from `/etc/vllm/vllm.env`, which vLLM supports, and omits
`--api-key` from `ExecStart`. Because the prior key had been exposed through
service arguments, it was treated as compromised. A new per-environment key was
generated and the v2 instances were force-replaced. Network resources were
preserved.

Both v2 subnets use an explicitly empty security list so OCI's default security
list cannot broaden access. The NSGs provide the intended rules: SSH from the
current admin `/32`, no public TCP/8080 rule, and private SSH/TCP/8000 from the
orchestrator to vLLM.

Post-rotation validation passed:

- SSH to the orchestrator passed.
- Orchestrator cloud-init reported `done` with no errors.
- `chronos-ml.service` and `forecast-orchestrator.service` were active.
- Local Chronos `/health` and orchestrator `/health` returned `status=ok`.
- Chronos preload succeeded with the expected public model.
- Private SSH to vLLM through the orchestrator passed.
- vLLM cloud-init reported `done` with no errors.
- `vllm-openai.service` was active.
- The vLLM service `MainPID` command line no longer contained `--api-key`.
- Authenticated private vLLM `/v1/models` from the orchestrator returned
  `Qwen/Qwen3-0.6B`.
- The Scenario 01 `/predict` smoke test completed with Chronos-2 output, no
  warnings, and non-fallback `Qwen/Qwen3-0.6B` explanation and recommendations.
- Public TCP/8080 denial passed; direct public `/health` timed out as expected.
- Final Terraform drift check passed.

## Known Gaps

- Scenario 01 evidence is intentionally redacted; raw environment files,
  secrets, Terraform state, saved plans, and full sensitive OCI inventory remain
  out of the repository.
- Keep the v1 control deployment intact while v2 evolves through Intel migration
  and dual-routing scenarios.
- Scenario 02 still needs Intel `VM.Standard4.Ax.Flex` quota/capacity and
  Terraform migration behavior validation.
