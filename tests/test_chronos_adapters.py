import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd

from ml_service.app.config import MLSettings
from ml_service.app.forecasting import ForecastingService
from ml_service.app.schemas import ForecastRequest


class FakeChronos2Pipeline:
    def __init__(self):
        self.calls = []

    def predict_df(self, **kwargs):
        self.calls.append(kwargs)
        prediction_length = kwargs["prediction_length"]
        levels = kwargs["quantile_levels"]
        result = {
            kwargs["id_column"]: [kwargs["df"][kwargs["id_column"]].iloc[0]] * prediction_length,
            "timestamp": pd.date_range("2000-01-05", periods=prediction_length, freq="D"),
            "target_name": [kwargs["target"]] * prediction_length,
            "predictions": [999.0] * prediction_length,
        }
        for level in levels:
            result[str(level)] = [100.0 + step + level * 10 for step in range(prediction_length)]
        return pd.DataFrame(result)


class FakeLegacyChronosPipeline:
    def __init__(self):
        self.calls = []

    def predict(self, context, prediction_length, num_samples):
        self.calls.append((context, prediction_length, num_samples))
        return np.asarray(
            [
                [
                    [10.0, 20.0],
                    [12.0, 22.0],
                    [14.0, 24.0],
                ]
            ]
        )


def _settings(**overrides):
    values = {
        "load_public_model": True,
        "force_fallback": False,
        "preload_model": False,
        "max_prediction_length": 96,
    }
    values.update(overrides)
    return MLSettings(**values)


def test_chronos2_builds_dataframes_and_maps_direct_quantiles():
    pipeline = FakeChronos2Pipeline()
    service = ForecastingService(_settings(), pipeline=pipeline, pipeline_family="chronos2")
    request = ForecastRequest(
        series_id="store-7",
        values=[10, 12, 15, 18],
        timestamps=["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
        prediction_length=2,
        quantile_levels=[0.1, 0.9],
        past_covariates={
            "promotion": [0, 0, 1, 1],
            "region": ["north", "north", "north", "north"],
        },
        future_covariates={
            "promotion": [1, 0],
            "region": ["north", "south"],
        },
        future_timestamps=["2026-07-05", "2026-07-06"],
    )

    response = service.predict(request)

    assert response.engine == "chronos"
    assert response.model_family == "chronos2"
    assert response.covariates_used.past == ["promotion", "region"]
    assert response.covariates_used.future == ["promotion", "region"]
    assert [point.timestamp for point in response.horizon] == ["2026-07-05", "2026-07-06"]
    assert response.horizon[0].median == 105.0
    assert response.horizon[0].median != 999.0

    call = pipeline.calls[0]
    context_df = call["df"]
    future_df = call["future_df"]
    assert context_df.columns.tolist() == ["item_id", "timestamp", "target", "promotion", "region"]
    assert context_df["target"].tolist() == [10.0, 12.0, 15.0, 18.0]
    assert context_df["promotion"].tolist() == [0, 0, 1, 1]
    assert context_df["region"].tolist() == ["north"] * 4
    assert context_df["timestamp"].diff().dropna().nunique() == 1
    assert future_df["promotion"].tolist() == [1, 0]
    assert future_df["region"].tolist() == ["north", "south"]
    assert call["quantile_levels"] == [0.1, 0.5, 0.9]


def test_chronos2_univariate_request_without_timestamps_keeps_response_timestamps_absent():
    pipeline = FakeChronos2Pipeline()
    service = ForecastingService(_settings(), pipeline=pipeline, pipeline_family="chronos2")

    response = service.predict(ForecastRequest(values=[1, 2, 3], prediction_length=2))

    assert response.engine == "chronos"
    assert response.model_family == "chronos2"
    assert response.covariates_used.past == []
    assert response.covariates_used.future == []
    assert [point.timestamp for point in response.horizon] == [None, None]
    assert pipeline.calls[0]["future_df"] is None


def test_chronos2_remaps_internal_columns_when_covariate_names_collide():
    pipeline = FakeChronos2Pipeline()
    service = ForecastingService(_settings(), pipeline=pipeline, pipeline_family="chronos2")

    response = service.predict(
        ForecastRequest(
            values=[1, 2, 3],
            prediction_length=1,
            past_covariates={
                "item_id": ["a", "a", "a"],
                "timestamp": ["morning", "noon", "night"],
                "target": [5, 6, 7],
            },
            future_covariates={
                "item_id": ["a"],
                "timestamp": ["morning"],
                "target": [8],
            },
        )
    )

    call = pipeline.calls[0]
    assert response.engine == "chronos"
    assert response.covariates_used.past == ["item_id", "target", "timestamp"]
    assert call["id_column"] != "item_id"
    assert call["timestamp_column"] != "timestamp"
    assert call["target"] != "target"
    assert call["df"]["item_id"].tolist() == ["a", "a", "a"]
    assert call["future_df"]["target"].tolist() == [8]


def test_legacy_chronos_adapter_remains_sample_based(monkeypatch):
    torch_stub = SimpleNamespace(
        float32="float32",
        tensor=lambda values, dtype: np.asarray(values, dtype=np.float32),
    )
    monkeypatch.setitem(sys.modules, "torch", torch_stub)
    pipeline = FakeLegacyChronosPipeline()
    service = ForecastingService(
        _settings(
            model_name="amazon/chronos-t5-small",
            model_revision=None,
            model_source_url="https://huggingface.co/amazon/chronos-t5-small",
            chronos_num_samples=3,
        ),
        pipeline=pipeline,
        pipeline_family="chronos",
    )

    response = service.predict(ForecastRequest(values=[5, 6, 7], prediction_length=2))

    assert response.engine == "chronos"
    assert response.model_family == "chronos"
    assert response.horizon[0].median == 12.0
    assert pipeline.calls[0][1:] == (2, 3)


def test_irregular_timestamps_are_warned_and_modeled_on_internal_index():
    pipeline = FakeChronos2Pipeline()
    service = ForecastingService(_settings(), pipeline=pipeline, pipeline_family="chronos2")

    response = service.predict(
        ForecastRequest(
            values=[1, 2, 3],
            timestamps=["2026-07-01", "2026-07-03", "2026-07-04"],
            prediction_length=1,
        )
    )

    assert response.engine == "chronos"
    assert any("evenly spaced internal index" in warning for warning in response.warnings)
    assert pipeline.calls[0]["df"]["timestamp"].diff().dropna().nunique() == 1


def test_preload_status_is_visible_in_health():
    service = ForecastingService(
        _settings(preload_model=True),
        pipeline=FakeChronos2Pipeline(),
        pipeline_family="chronos2",
    )

    assert service.preload() is True
    health = service.health()
    assert health["model_family"] == "chronos2"
    assert health["preload_attempted"] is True
    assert health["preload_succeeded"] is True
    assert health["load_error"] is None


def test_loading_uses_base_pipeline_pinned_revision_and_persistent_cache(monkeypatch, tmp_path):
    calls = []

    class FakeBaseChronosPipeline:
        @classmethod
        def from_pretrained(cls, model_name, **kwargs):
            calls.append((model_name, kwargs))
            return FakeChronos2Pipeline()

    chronos_module = ModuleType("chronos")
    chronos_module.BaseChronosPipeline = FakeBaseChronosPipeline
    monkeypatch.setitem(sys.modules, "chronos", chronos_module)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float32="float32"))
    service = ForecastingService(_settings(hf_home=str(tmp_path)))

    assert service.preload() is True
    model_name, kwargs = calls[0]
    assert model_name == "autogluon/chronos-2-small"
    assert kwargs["revision"] == "ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a"
    assert kwargs["cache_dir"] == str(tmp_path)
    assert kwargs["device_map"] == "cpu"
    assert kwargs["torch_dtype"] == "float32"


def test_explicit_legacy_model_settings_do_not_inherit_chronos2_defaults(monkeypatch):
    monkeypatch.delenv("CHRONOS_MODEL_REVISION", raising=False)
    monkeypatch.delenv("CHRONOS_MODEL_SOURCE_URL", raising=False)
    settings = MLSettings(model_name="amazon/chronos-t5-small")

    assert settings.model_revision is None
    assert settings.model_source_url == "https://huggingface.co/amazon/chronos-t5-small"
