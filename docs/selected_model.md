# Selected Public Model

The selected non-vLLM inference model is `autogluon/chronos-2-small`.

Source: https://huggingface.co/autogluon/chronos-2-small

Pinned checkpoint revision: `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a`

Pinned package: `chronos-forecasting==2.3.1`

Category: pretrained time-series forecasting transformer.

Role in this project:

- Serve zero-shot probabilistic forecasts from one historical numeric target series.
- Use real-valued, categorical, or boolean historical and known-future covariates when supplied.
- Return normalized forecast summaries, risk bands, confidence, and proxy driver contributions.
- Stay separate from the vLLM service. Chronos handles numeric forecasting; vLLM handles explanation and recommendation text.

Operational notes:

- The service uses CPU by default for OCI E6 AX compatibility.
- The public model is preloaded during FastAPI startup when `ML_PRELOAD_MODEL=true`; lazy loading remains available when preload is disabled.
- Model loading goes through `BaseChronosPipeline.from_pretrained`. Chronos-2 uses `predict_df` and direct requested quantiles.
- CPU float32 is the initial OCI E6 AX configuration, with `MAX_PREDICTION_LENGTH=96` and a persistent application-local Hugging Face cache.
- If Chronos dependencies, model download, or inference fail, the service returns a deterministic trend fallback and includes a warning.
- The fallback ignores covariates and reports `model_family="fallback"`; `covariates_used` is empty.
- `drivers` are target-history heuristics and are not model attribution or permutation feature importance.
- This project does not train or fine-tune Chronos.

## Rollback Model

The dual-adapter code retains `amazon/chronos-t5-small`. It uses the original sampled-trajectory adapter and `CHRONOS_NUM_SAMPLES`; covariates are intentionally ignored with a warning. Rollback changes only `CHRONOS_MODEL_NAME`, `CHRONOS_MODEL_SOURCE_URL`, and `CHRONOS_MODEL_REVISION` in the protected host environment, then restarts `chronos-ml.service`. No code rollback is required.

Production caveats to check:

- Apache-2.0 license and any dependency licenses.
- Latency and memory on the exact E6 AX shape.
- Forecast quality on the target domain and forecast horizon.
- Weighted quantile loss and MASE versus the original Chronos model on representative holdouts, including a covariate-bearing dataset.
- Twenty-request fallback-free smoke behavior, warm p95 latency, preload time, and peak resident memory on the existing 8-OCPU E6 AX host.
