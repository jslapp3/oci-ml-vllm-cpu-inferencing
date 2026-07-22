# OCI Terraform Scaffold

This optional scaffold creates the full two-VM MVP:

- public orchestrator/Chronos VM
- private Qwen/vLLM VM
- VCN, public/private subnets, internet and NAT gateways
- route tables and narrowly scoped NSGs
- cloud-init bootstrap for both services

The manually deployed v1 environment works. The Terraform-managed v2 AMD
baseline completed a fresh end-to-end apply and smoke validation on 2026-07-21.
Future shape migrations and dual-vLLM routing changes should still be validated
with a reviewed plan before apply.

## Prerequisites

- Terraform 1.5 or newer
- OCI provider credentials and a suitable compartment
- quota for two `VM.Standard.E6.Ax.Flex` instances
- an SSH key pair
- a pushed application repository commit
- an Oracle Linux image with Python 3.11 available

The pinned Chronos package requires Python 3.10 or newer. Verify the selected image and cloud-init package availability before applying; Python 3.9 will fail during bootstrap.

The bootstrap installs the Python 3.11 package stream for Chronos and fails if
that interpreter is unavailable. The vLLM host pins managed Python 3.12.13,
uv 0.11.28, and vLLM 0.24.0 against the matching CPU wheel index. Update these
versions deliberately and regenerate the reviewed plan when upgrading.

## Configure

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set at least:

```hcl
compartment_ocid    = "ocid1.compartment.oc1..example"
availability_domain = "EXAMPLE:US-ASHBURN-AD-1"
ssh_public_key_path = "~/.ssh/id_ed25519.pub"

admin_cidr_blocks      = ["your.public.ip/32"]
public_api_cidr_blocks = ["your.public.ip/32"]

app_repo_url = "https://github.com/<owner>/<repo>.git"
app_repo_ref = "<tested-commit-sha>"
vllm_model    = "Qwen/Qwen3-0.6B"
vllm_api_key  = "<random-long-token>"
```

Find your public IP and generate a key with:

```bash
curl -s https://ifconfig.me/ip
openssl rand -hex 32
```

Do not commit `terraform.tfvars`, state files, `.terraform/`, private keys, or generated credentials.

## Apply

```bash
terraform init
terraform fmt -check -recursive
terraform plan
terraform apply
```

Capture the outputs:

```bash
terraform output
terraform output -raw orchestrator_public_ip
terraform output -raw vllm_private_ip
```

Instances may report running before cloud-init finishes. On the orchestrator:

```bash
ssh opc@<orchestrator-public-ip>
sudo cloud-init status --wait
sudo systemctl status chronos-ml.service
sudo systemctl status forecast-orchestrator.service
curl -fsS http://127.0.0.1:8080/health | python3 -m json.tool
```

Inspect the private Qwen VM through the orchestrator:

```bash
ssh -J opc@<orchestrator-public-ip> opc@<vllm-private-ip>
sudo cloud-init status --wait
sudo systemctl status vllm-openai.service
```

## Update The Application

Use the same exact-commit workflow as the main [operations runbook](../../docs/runbook.md):

```bash
cd <source-checkout>
git fetch origin
git checkout <tested-commit-sha>
sudo env PYTHON_BIN=python3.11 deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

Changing the cloud-init template does not update an existing VM. Do not apply Terraform merely to deploy application code.

## Destroy

For a disposable test stack:

```bash
terraform destroy
```

## Security

Sensitive Terraform variables still enter state and instance metadata. Before production use, move secrets to OCI Vault, add authenticated ingress, export service logs, and validate replacement behavior in every Terraform plan.
