# Validation Record

The application and live smoke tests are working. For the current architecture
demo, validation is intentionally focused on service topology, routing readiness,
and non-fallback behavior rather than forecast-quality benchmarking.

## Pinned Models

| Family | Model | Revision | Package |
| --- | --- | --- | --- |
| Current | `autogluon/chronos-2-small` | `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a` | `chronos-forecasting==2.3.1` |
| Rollback | `amazon/chronos-t5-small` | repository default | `chronos-forecasting==2.3.1` |

Both use CPU float32 and `MAX_PREDICTION_LENGTH=96`. `CHRONOS_NUM_SAMPLES` applies only to the rollback model.

## Model-Quality Backtests

Full WQL/MASE backtesting is not a gate for the architecture demo. The numeric
model remains the current Chronos-2 checkpoint listed above. The rollback model
exists for operations safety, but it is not part of the demo validation path.

| Date | Dataset/window | Covariates | Model | WQL | MASE | Notes |
| --- | --- | --- | --- | ---: | ---: | --- |
| Deferred | Deferred | Deferred | Chronos-2 | Deferred | Deferred | Not required for architecture demo |

If model-quality work becomes important later, use identical histories, holdout
windows, horizons, and quantiles, and record the seasonal-naive denominator used
for MASE. Do not put private dataset contents in this file.

## Architecture Validation Gates

| Gate | Required | Result | Status |
| --- | --- | --- | --- |
| Consecutive requests | 5 without deterministic fallback | Pending | Pending |
| Current model | `autogluon/chronos-2-small` at pinned revision | Smoke passed; 5-run record pending | Pending |
| Forecast engine | `ml_output.engine="chronos"` | Smoke passed; 5-run record pending | Pending |
| Model family | `ml_output.model_family="chronos2"` | Smoke passed; 5-run record pending | Pending |
| vLLM language path | non-fallback explanation and recommendations | Smoke passed; 5-run record pending | Pending |
| Forecast integrity | finite, nondecreasing quantiles and exact horizon | Smoke passed; full run pending | Pending |
| Covariate reporting | expected past and future names | Smoke passed; full run pending | Pending |
| Rough latency | record observed timings, no strict p95 gate | Pending | Pending |

Strict warm p95, peak RSS, and original-Chronos comparison gates are deferred.
Do not change the VM shape, horizon, or model just to turn a failed smoke gate
into a pass. Record the observed result and investigate the architecture path
separately.

Operational commands and rollback are in the [runbook](runbook.md).
