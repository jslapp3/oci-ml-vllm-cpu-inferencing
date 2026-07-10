# OCI Terraform Scaffold

This directory is a repeatable Terraform starting point for the current MVP topology:

- one VCN
- one public subnet for the orchestrator/Chronos VM
- one private subnet for the CPU vLLM VM
- an internet gateway for the public subnet
- a NAT gateway for private subnet outbound downloads
- NSGs with narrow ingress rules
- two `VM.Standard.E6.Ax.Flex` instances
- cloud-init for the orchestrator and CPU vLLM services

The current hand-built environment is the model for this scaffold:

- public orchestrator/Chronos API on TCP/8080
- private vLLM OpenAI-compatible endpoint on TCP/8000
- vLLM reachable only from the orchestrator private IP
- SSH to the private vLLM host through the public orchestrator host

## Files

- `versions.tf` - provider and Terraform version constraints.
- `provider.tf` - OCI provider configuration.
- `variables.tf` - inputs for tenancy, compartment, region, CIDRs, shapes, keys, and runtime settings.
- `locals.tf` - common labels and image selection helper.
- `network.tf` - VCN, gateways, route tables, DHCP options, and subnets.
- `security.tf` - NSGs and role-specific ingress/egress rules.
- `compute.tf` - orchestrator and vLLM Compute instances.
- `outputs.tf` - IPs and SSH helper commands.
- `cloud-init/orchestrator.yaml.tftpl` - installs this app and starts Chronos/orchestrator services.
- `cloud-init/vllm-cpu.yaml.tftpl` - installs vLLM CPU with AMD Zen support and starts the private server.
- `terraform.tfvars.example` - copy to `terraform.tfvars` and fill in real values.

## Usage

For a friend-facing walkthrough, start with [QUICKSTART.md](QUICKSTART.md).

Copy the example variables file:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit values:

```bash
nano terraform.tfvars
```

At minimum, set:

- `compartment_ocid`
- `availability_domain`
- `ssh_public_key_path`
- `admin_cidr_blocks`
- `public_api_cidr_blocks`
- `app_repo_url`
- `vllm_api_key`

Then run:

```bash
terraform init
terraform fmt
terraform plan
terraform apply
```

## Secrets Warning

`vllm_api_key` and `hf_token` are marked sensitive, but values used by cloud-init are still stored in Terraform state and instance metadata. This is acceptable for a first repeatable MVP, but production hardening should move secrets to OCI Vault and fetch them on boot using instance principals.

Do not commit `terraform.tfvars`, Terraform state files, `.terraform/`, or any generated private keys.

## Post-Apply Checks

From your local machine:

```bash
ssh -i ~/.ssh/id_ed25519 opc@<orchestrator_public_ip>
curl -i http://127.0.0.1:8080/health
```

From the orchestrator VM:

```bash
curl -i http://<vllm_private_ip>:8000/health
```

For private vLLM SSH through the orchestrator:

```bash
ssh -i ~/.ssh/id_ed25519 -J opc@<orchestrator_public_ip> opc@<vllm_private_ip>
```

## Known Follow-Ups

- Move secrets from cloud-init/Terraform state to OCI Vault.
- Add image pinning once you choose an Oracle Linux image OCID for your region.
- Add optional Load Balancer or API Gateway in front of the orchestrator.
- Add OCI Logging exports for the systemd services.
- Convert cloud-init shell blocks into versioned scripts if they grow much more.
