# Validation Record

The application and live smoke tests are working. The following quality and capacity checks remain before treating the MVP as production-ready.

## Pinned Models

| Family | Model | Revision | Package |
| --- | --- | --- | --- |
| Current | `autogluon/chronos-2-small` | `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a` | `chronos-forecasting==2.3.1` |
| Rollback | `amazon/chronos-t5-small` | repository default | `chronos-forecasting==2.3.1` |

Both use CPU float32 and `MAX_PREDICTION_LENGTH=96`. `CHRONOS_NUM_SAMPLES` applies only to the rollback model.

## Backtests

Use identical histories, holdout windows, horizons, and quantiles for both families. Include at least one dataset with useful historical and known-future covariates. Do not put private dataset contents in this file.

| Date | Dataset/window | Covariates | Model | WQL | MASE | Notes |
| --- | --- | --- | --- | ---: | ---: | --- |
| Pending | Pending | Pending | Original Chronos | Pending | Pending | Not run |
| Pending | Pending | Pending | Chronos-2 | Pending | Pending | Not run |

Record the seasonal-naive denominator used for MASE.

## Host Gates

| Gate | Required | Result | Status |
| --- | --- | --- | --- |
| Consecutive requests | 20 without deterministic fallback | Pending | Pending |
| Warm ML inference p95 | `< 20 seconds` | Pending | Pending |
| Startup preload | `< 300 seconds` | Pending | Pending |
| Peak ML-service RSS | `< 8 GB` | Pending | Pending |
| Forecast integrity | finite, nondecreasing quantiles and exact horizon | Smoke passed; full run pending | Pending |
| Covariate reporting | expected past and future names | Smoke passed; full run pending | Pending |

Do not increase the VM shape or horizon merely to turn a failed gate into a pass. Record the measured result and investigate capacity or model suitability separately.

Operational commands and rollback are in the [runbook](runbook.md).
