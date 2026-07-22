# Scenario Records

This directory tracks the architecture-demo scenarios for the project.

Each scenario should record:

- intent;
- topology;
- Terraform variables used;
- runtime differences;
- validation commands;
- observed results;
- known gaps.

## Scenarios

| Scenario | Status | Purpose |
| --- | --- | --- |
| [01 AMD Baseline](01-amd-baseline.md) | Passed | Prove the current Terraform two-VM baseline works cleanly. |
| [02 AMD To Intel Recreation](02-amd-to-intel-migration.md) | Passed | Proved the AMD deployment pattern can be recreated on Intel with no app-code change. |
| [03 Dual vLLM Routing](03-dual-vllm-routing.md) | Planned | Prove one deployment can route vLLM language inference across AMD and Intel. |

Do not store raw secrets, private keys, Terraform state, or unredacted environment files here.
