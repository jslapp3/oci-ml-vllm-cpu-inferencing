# Chronos-2 Small Migration Plan

## Goal

Replace `amazon/chronos-t5-small` with `autogluon/chronos-2-small` while retaining the existing FastAPI, orchestrator, systemd, OCI Compute, vLLM, and deterministic fallback architecture.

Use a staged, backward-compatible migration:

1. Add Chronos-2 support while the original model remains selectable through configuration.
2. Switch the deployed default to Chronos-2 and benchmark it on the existing OCI E6 AX host.
3. Enable historical and known-future covariates through the JSON and CSV interfaces.
4. Retain the original Chronos adapter for immediate rollback.

Chronos-2 must remain a zero-shot model in this architecture. Do not add per-dataset training, fine-tuning, or AutoGluon-TimeSeries.

## Effort And Risk

| Area | Pain | Assessment |
| --- | ---: | --- |
| Basic univariate model swap | 2/10 | Same Python package and ML service; inference and output mapping change |
| OCI/systemd deployment | 2/10 | No new service, port, VM, GPU, or Terraform resource |
| Dependency/runtime validation | 4/10 | Pin and test package/model revisions on Oracle Linux CPU |
| Covariate-enabled JSON API | 5/10 | Add schemas, alignment validation, and model-input construction |
| Covariate-enabled CSV flow | 7/10 | The current parser discards future blank-target rows and sends covariates only to the LLM |
| Overall migration | 5/10 | Approximately 3-5 engineering days including tests and deployment validation |

## Model Service

Update the ML service to:

- Load models through `BaseChronosPipeline.from_pretrained`.
- Detect whether the loaded pipeline is original Chronos or Chronos-2 and route it to the corresponding inference adapter.
- Use Chronos-2 `predict_df`, passing requested quantiles directly instead of generating sampled trajectories with `CHRONOS_NUM_SAMPLES`.
- Construct historical and optional future dataframes containing the target, internal timestamps, and covariates.
- Preserve the current normalized horizon, forecast summary, warnings, heuristic drivers, and deterministic fallback.
- Keep `engine="chronos"` for response compatibility and add `model_family="chronos2"` plus the historical and future covariates used.
- Continue treating `drivers` as heuristic indicators, not model attribution. Do not add expensive permutation feature importance.
- Ignore covariates when deterministic fallback is used and add an explicit warning explaining that behavior.
- Optionally preload the model during service startup so the first user request does not absorb model loading latency.

Keep the original Chronos inference adapter as a rollback path. It does not need new covariate support.

## Public Request Interface

Keep every existing request field and add these optional fields to both the orchestrator and ML request schemas:

```json
{
  "past_covariates": {
    "promotion": [0, 0, 1],
    "region": ["north", "north", "north"]
  },
  "future_covariates": {
    "promotion": [1, 1]
  },
  "future_timestamps": ["2026-07-04", "2026-07-05"]
}
```

Apply these validation rules:

- Historical covariate arrays must have the same length as `values`.
- Future covariate arrays and `future_timestamps` must have length `prediction_length`.
- A future-known covariate must also have historical values.
- Covariate values may be finite numbers, strings, or booleans.
- Reject mixed scalar types within one covariate, excluding compatible integer/float mixtures.
- Requests without covariates remain valid and run as univariate zero-shot forecasts.
- Requests without timestamps use an internal evenly spaced synthetic index while preserving the existing response behavior for absent timestamps.
- Irregular supplied timestamps are modeled as ordered, equally spaced observations and produce a warning rather than breaking an existing request.

Multivariate targets and multi-series batch requests are out of scope. Continue supporting one target series per request.

## Response Interface

Preserve the existing response shape and add:

- `model_family`: `chronos2`, `chronos`, or `fallback` as appropriate.
- `covariates_used`: an object containing `past` and `future` name lists.

Keep `engine="chronos"` for both real Chronos families and `engine="fallback"` for deterministic fallback. Preserve JSON, Markdown, and enriched CSV response formats.

## CSV Ingestion

Extend the current CSV workflow as follows:

- Continue treating every non-date, non-target column as a candidate covariate.
- Send complete historical covariate columns to Chronos-2 instead of only summarizing them for the LLM.
- Interpret contiguous trailing rows with blank targets as future-known rows.
- If trailing future rows are present, require their count to equal `prediction_length`.
- Treat covariates complete across history and the future rows as known-future covariates.
- Treat covariates complete in history but not in the future rows as past-only covariates.
- Exclude incomplete covariate columns from model input with a warning while retaining their values and summaries for presentation and LLM context.
- Continue handling blank-target rows inside historical data according to existing behavior, with warnings.
- Keep enriched CSV output useful by retaining original covariate values on actual and future rows.

## Dependencies And Configuration

- Pin `chronos-forecasting==2.3.1` in the ML requirements.
- Use `CHRONOS_MODEL_NAME=autogluon/chronos-2-small`.
- Use `CHRONOS_MODEL_REVISION=ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a`.
- Update `CHRONOS_MODEL_SOURCE_URL` to the matching Hugging Face model page.
- Add `ML_PRELOAD_MODEL=true` if startup preloading is implemented.
- Configure a persistent Hugging Face cache under the application directory rather than a temporary location.
- Continue using CPU float32 initially.
- Keep `MAX_PREDICTION_LENGTH=96` initially to protect CPU capacity.
- Retain `CHRONOS_NUM_SAMPLES` only for the legacy Chronos adapter and mark it deprecated in examples and documentation.
- Raise `ML_SERVICE_TIMEOUT_SECONDS` from 20 to 30 seconds pending benchmark results.
- Pin model and package versions; do not modify or expose the live `.env` file.

Update `.env.example`, `deploy/compute.env.example`, Terraform cloud-init defaults, deployment notes, the architecture document, the selected-model document, and the README.

No OCI shape, port, firewall, load balancer, vLLM service, or Terraform resource changes are expected.

## Testing

Add or update tests for:

- Chronos-2 dataframe construction and direct quantile-to-response mapping using a fake pipeline.
- Original Chronos adapter compatibility.
- Univariate requests with and without timestamps.
- Numeric and categorical historical covariates.
- Numeric and categorical known-future covariates.
- Covariate length mismatches and mixed-type rejection.
- Incomplete CSV covariates and warning behavior.
- CSV trailing future rows and propagation into the ML request.
- Irregular timestamp warning behavior.
- Deterministic fallback with and without covariates.
- Existing JSON, Markdown, enriched CSV, orchestration, database, and vLLM fallback behavior.

Ordinary unit tests must not download model weights. Add a separately marked, opt-in integration test that downloads the pinned checkpoint and performs one CPU forecast.

Run the complete unit test suite after implementation.

## Benchmark And Acceptance Gates

Backtest original Chronos and Chronos-2 on representative holdout windows using weighted quantile loss and MASE. Include at least one dataset with useful covariates.

Before enabling Chronos-2 in deployment, verify:

- The service produces no deterministic fallback in 20 consecutive smoke requests.
- Warm p95 inference latency remains below the existing 20-second service objective on the 8-OCPU E6 AX host.
- Preload/startup completes within systemd's 300-second startup limit.
- Peak ML-service resident memory stays below 8 GB.
- Forecast responses contain finite, ordered quantiles and the requested horizon length.
- Covariate requests report the expected `covariates_used` names.

Do not increase the OCI shape or maximum horizon merely to make the initial migration pass. Record benchmark results and revisit capacity separately.

## Deployment And Rollback

Roll out in this order:

1. Deploy the dual-adapter code while the existing environment still selects `amazon/chronos-t5-small`.
2. Run regression and smoke tests against the original model.
3. Update the existing host's protected environment file with the Chronos-2 model name, source, revision, preload setting, and timeout.
4. Reinstall the pinned ML requirements if needed and restart `chronos-ml.service`.
5. Confirm health reports the pinned model, successful preload, and no load error.
6. Run univariate and covariate smoke requests through the orchestrator.
7. Enable covariate-bearing clients after the benchmark gates pass.

Rollback must require only restoring the original model name, source, and revision in the protected environment file and restarting `chronos-ml.service`. A code rollback must not be required.

## Implementation Guardrails

- Inspect the current code before editing and follow its existing patterns.
- Do not read, print, overwrite, or commit the live `.env` file.
- Do not modify or delete untracked dataset files.
- Do not introduce AutoGluon-TimeSeries or a training pipeline.
- Do not remove the deterministic fallback.
- Do not claim heuristic drivers are Chronos-2 feature attribution.
- Keep changes focused on this migration and avoid unrelated refactoring.
- At completion, report changed files, tests run, tests not run, existing-host deployment commands, and the exact environment-variable rollback procedure.

