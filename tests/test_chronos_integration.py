import os

import pytest

from ml_service.app.config import MLSettings
from ml_service.app.forecasting import ForecastingService
from ml_service.app.schemas import ForecastRequest


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_CHRONOS_INTEGRATION") != "1",
    reason="set RUN_CHRONOS_INTEGRATION=1 to download and test the pinned Chronos-2 checkpoint",
)
def test_pinned_chronos2_checkpoint_runs_one_cpu_forecast():
    service = ForecastingService(MLSettings(device="cpu", preload_model=False))
    response = service.predict(
        ForecastRequest(
            series_id="integration-smoke",
            values=[10, 11, 13, 12, 15, 16],
            prediction_length=2,
        )
    )

    assert response.engine == "chronos"
    assert response.model_family == "chronos2"
    assert response.model_version == "ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a"
    assert len(response.horizon) == 2
    assert all(point.lower <= point.median <= point.upper for point in response.horizon)
