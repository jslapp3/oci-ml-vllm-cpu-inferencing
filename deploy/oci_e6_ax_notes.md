# OCI Production Path Notes

## OCI Compute on E6 AX

The MVP runtime target is OCI Compute on an E6 AX shape using Python virtual environments and systemd services.

The pinned `autogluon/chronos-2-small` checkpoint runs in CPU float32 and preloads at service startup. The original `amazon/chronos-t5-small` adapter remains deployed for environment-only rollback. Do not enable Chronos-2 clients until cold-load time, memory, disk use, forecast quality, and warm p95 latency are measured on the existing host.

The selected model is a forecasting transformer, not a classical scikit-learn model. It is still served outside vLLM because vLLM is optimized for LLM text generation and embeddings, not arbitrary forecasting pipelines.

## Dependency Strategy

The MVP uses:

- `requirements-ml.txt` for the Chronos ML service.
- `requirements-orchestrator.txt` for the orchestration API.
- Separate virtual environments under `/opt/oci-vllm-ml-inference`.
- `chronos-forecasting==2.3.1` and the pinned Chronos-2 checkpoint revision.
- `/opt/oci-vllm-ml-inference/hf_cache`, preserved by the installer, rather than a temporary model cache.

This avoids container and registry work while still isolating the heavy ML dependencies from the lighter orchestrator service.

If Torch/Chronos installs become flaky or slow, the next step is conda:

- Create an `environment.yml`.
- Validate it on an OCI build or Data Science host.
- Optionally pack it and store it in Object Storage.

## vLLM Placement

vLLM is best suited for GPU-backed LLM serving. Running vLLM on CPU-only E6 AX may work only for very small models or low-throughput experimentation and is not the recommended production path for responsive LLM explanations.

Production options:

- Run vLLM on a GPU-backed OCI Compute shape and point `VLLM_BASE_URL` at that private endpoint.
- Use OCI Data Science Model Deployment for the LLM or ML layer when managed deployment, autoscaling, and model lifecycle tooling matter more than direct service control.
- Use OCI Generative AI where a managed hosted model satisfies the explanation and recommendation requirements.

## When To Use OCI Data Science Model Deployment

Choose OCI Data Science Model Deployment when you need managed model serving, model versioning, scaling controls, IAM integration, and operational monitoring without maintaining service hosts directly.

Choose systemd-on-Compute when you need the simplest MVP path with direct control and minimal infrastructure dependencies.

## Networking And Security

- Put the Compute instance in a private subnet when possible.
- Expose the orchestrator through OCI Load Balancer or API Gateway.
- Do not expose the ML service directly; it binds to `127.0.0.1`.
- Use NSGs/security lists to restrict inbound traffic to the orchestrator.
- Keep ADB private endpoint access scoped to the orchestrator subnet.
- Store vLLM API keys, DB credentials, and wallet material in OCI Vault for hardened deployments.

## Logging And Monitoring

- Use `journalctl` for MVP service logs.
- Export systemd logs to OCI Logging as the deployment hardens.
- Log request IDs, model name, model revision, latency, fallback use, and error causes.
- Do not log sensitive raw input unless explicitly approved.
- Track ML service fallback rate and vLLM unavailable rate as production health signals.

## Scaling

- Start with one Compute instance for MVP.
- Move the ML service and orchestrator to separate Compute instances if resource contention appears.
- Use a Load Balancer across multiple orchestrator hosts for horizontal scale.
- Keep `MAX_PREDICTION_LENGTH=96` for both adapters. `CHRONOS_NUM_SAMPLES` is deprecated and protects capacity only when the original Chronos rollback adapter is selected.
- Consider OCI Data Science Model Deployment, OKE, or image-based deployment when single-host systemd is no longer enough.

## Chronos-2 Acceptance Record

Record weighted quantile loss and MASE for original Chronos and Chronos-2 on representative holdout windows, including at least one covariate-bearing dataset. Record the dataset/window definition and settings with each result.

The existing 8-OCPU E6 AX host must pass all gates before clients send covariates:

- no deterministic fallback across 20 consecutive smoke requests;
- warm p95 inference below 20 seconds;
- preload/health readiness within the 300-second startup ceiling;
- peak ML-service RSS below 8 GB;
- finite, nondecreasing requested quantiles at the exact requested horizon;
- correct historical and future names in `covariates_used`.

Do not increase the shape or maximum horizon to pass the initial migration. Exact staged deployment and environment-only rollback commands are in [compute_venv_deployment.md](compute_venv_deployment.md).

## Autonomous Database

The `db/schema.sql` file creates normalized tables for run logs, forecast points, driver contributions, LLM outputs, and a latest-success view. The initial app writes compact JSON payloads into `inference_runs`; normalized writes can be added once the response contract stabilizes.

## APEX And Oracle Analytics Cloud

APEX can call the orchestrator API through OCI API Gateway or Load Balancer. Oracle Analytics Cloud can query the ADB logging tables and `latest_successful_inference_v` for dashboards once inference logs are persisted.
