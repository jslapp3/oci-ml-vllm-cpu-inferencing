# Chronos-2 Migration Validation Record

Status: **pending execution on the existing 8-OCPU OCI E6 AX host**.

This record must be completed before Chronos-2 is enabled for covariate-bearing clients. Do not convert a pending entry to pass without retaining the raw run date, dataset/window definition, and measured value.

## Pinned Candidates

| Family | Model | Revision | Package |
| --- | --- | --- | --- |
| Original Chronos | `amazon/chronos-t5-small` | blank / repository default | `chronos-forecasting==2.3.1` |
| Chronos-2 | `autogluon/chronos-2-small` | `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a` | `chronos-forecasting==2.3.1` |

Both candidates use CPU float32 and `MAX_PREDICTION_LENGTH=96`. `CHRONOS_NUM_SAMPLES` applies only to original Chronos.

## Backtest Results

Add one row per representative dataset and holdout window. At least one row must use useful historical and known-future covariates with Chronos-2. Never put private dataset contents in this file.

| Run date | Dataset/window identifier | Covariates | Model family | Weighted quantile loss | MASE | Notes |
| --- | --- | --- | --- | ---: | ---: | --- |
| Pending | Pending | Pending | Original Chronos | Pending | Pending | Not run in the unit-test workspace |
| Pending | Pending | Pending | Chronos-2 | Pending | Pending | Not run in the unit-test workspace |

Use the same target history, holdout windows, horizons, and requested quantiles for both model families. Compute MASE using an in-sample naive scaling denominator appropriate to the dataset frequency, and record that seasonality choice.

## Existing-Host Acceptance Gates

| Gate | Required | Recorded result | Status |
| --- | --- | --- | --- |
| Consecutive smoke requests | 20 with no deterministic fallback | Pending | Pending |
| Warm ML inference p95 | `< 20 seconds` | Pending | Pending |
| Startup preload readiness | `< 300 seconds` | Pending | Pending |
| Peak ML-service RSS | `< 8 GB` | Pending | Pending |
| Forecast integrity | finite, nondecreasing quantiles; exact horizon | Pending | Pending |
| Covariate reporting | expected past/future names | Pending | Pending |

Do not increase the OCI shape or maximum horizon to turn a failed gate into a pass. Record the failure and review capacity separately.

The staged commands and exact rollback procedure are in [the OCI Compute deployment guide](../deploy/compute_venv_deployment.md).
