# Terraform Quickstart

This quickstart is for someone who has cloned the repo and wants to stand up the full OCI MVP stack, then run a public `/predict` call from their laptop.

Important: this Terraform scaffold has not been end-to-end tested yet. It was created from the manually working deployment and should be tested soon in a disposable OCI compartment before treating it as friend-proof or production-ready.

## What This Creates

- A VCN with public and private subnets.
- Internet and NAT gateways.
- Route tables for public and private traffic.
- NSGs for narrow SSH, public API, and private vLLM access.
- A public `VM.Standard.E6.Ax.Flex` orchestrator/Chronos VM.
- A private `VM.Standard.E6.Ax.Flex` CPU vLLM VM.
- Cloud-init bootstrap for both VMs.

The final public call goes to:

```text
http://<orchestrator_public_ip>:8080/predict
```

## Prerequisites

Install and configure:

- Terraform 1.5 or newer.
- OCI CLI credentials, or equivalent Terraform OCI provider credentials.
- An OCI compartment where your user can manage networking and Compute.
- OCI quota/capacity for two `VM.Standard.E6.Ax.Flex` instances.
- An SSH key pair on your laptop.

If needed, create an SSH key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

Find your current public IP:

```bash
curl -s https://ifconfig.me/ip
```

Use that value with `/32` in the allowlists, for example:

```text
203.0.113.10/32
```

## Configure OCI Auth

If you use the OCI CLI profile flow:

```bash
oci setup config
```

Make sure this works:

```bash
oci iam region list
```

The Terraform provider can also be configured with explicit OCIDs and key paths in `terraform.tfvars`.

## Configure Variables

From the repo root:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

Set at least:

```hcl
region              = "us-ashburn-1"
compartment_ocid    = "ocid1.compartment.oc1..example"
availability_domain = "EXAMPLE:US-ASHBURN-AD-1"

ssh_public_key_path = "~/.ssh/id_ed25519.pub"

admin_cidr_blocks      = ["your.public.ip/32"]
public_api_cidr_blocks = ["your.public.ip/32"]

app_repo_url = "https://github.com/<owner>/<repo>.git"
app_repo_ref = "main"

vllm_api_key = "replace-with-a-random-long-token"
```

Generate a local vLLM API key value with:

```bash
openssl rand -hex 32
```

For the first CPU vLLM demo, keep:

```hcl
vllm_model = "Qwen/Qwen3-0.6B"
```

## Apply

```bash
terraform init
terraform fmt
terraform plan
terraform apply
```

When apply finishes, capture the outputs:

```bash
terraform output
terraform output -raw orchestrator_public_ip
terraform output -raw vllm_private_ip
```

## Wait For Bootstrapping

The OCI instances can show as running before cloud-init has finished installing Python dependencies, Chronos, and vLLM.

SSH to the orchestrator VM:

```bash
ssh -i ~/.ssh/id_ed25519 opc@<orchestrator_public_ip>
```

Then wait and check services:

```bash
sudo cloud-init status --wait
sudo systemctl status chronos-ml.service
sudo systemctl status forecast-orchestrator.service
curl -i http://127.0.0.1:8080/health
```

Check private vLLM from the orchestrator VM:

```bash
curl -i http://<vllm_private_ip>:8000/health
```

If you need to inspect the private vLLM VM:

```bash
ssh -i ~/.ssh/id_ed25519 -J opc@<orchestrator_public_ip> opc@<vllm_private_ip>
sudo cloud-init status --wait
sudo systemctl status vllm-openai.service
```

## Run Public Predict

From your laptop:

```bash
curl --noproxy '*' -sS -i \
  -X POST http://<orchestrator_public_ip>:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "series_id": "public-demand-test",
    "timestamps": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
    "values": [120, 127, 131, 138],
    "prediction_length": 6,
    "notes": "Promotion starts next week and inventory is constrained.",
    "metadata": {"domain": "demand"}
  }'
```

Expected signs of success:

- HTTP `200 OK`.
- `ml_output.engine` is `chronos`.
- vLLM explanation/recommendation fields do not report template fallback.

## Updating The App After New GitHub Changes

On the orchestrator VM, pull the repo and rerun the existing installer. The installer preserves the existing `/etc/oci-forecast/forecast.env`.

```bash
cd ~/oci-ml-vllm-cpu-inferencing
git pull
sudo deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

If the repo is not already cloned on the VM:

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
sudo deploy/install_compute_venv.sh
sudo systemctl restart chronos-ml.service
sudo systemctl restart forecast-orchestrator.service
```

Then test locally on the VM:

```bash
curl -i http://127.0.0.1:8080/health
```

And rerun the public `/predict` curl from your laptop.

## Destroy

When finished with a test stack:

```bash
terraform destroy
```

This removes the OCI resources managed by this Terraform stack.

## Current Readiness

Ready for review and first end-to-end Terraform testing:

- The live architecture has been built manually.
- The Terraform files are formatted.
- The scaffold has not yet had a full `terraform init`, `plan`, and `apply` validation against a fresh OCI compartment.

Treat the first run as a test deployment, not a guaranteed one-click install.
