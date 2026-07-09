import asyncio

from orchestrator_api.app.config import OrchestratorSettings
from orchestrator_api.app.db import DatabaseWriter


def test_database_writer_is_optional_when_disabled():
    writer = DatabaseWriter(OrchestratorSettings(db_enabled=False))

    result = asyncio.run(
        writer.write_inference_run(
            run_id="run-1",
            request_payload={"series_id": "series-a"},
            response_payload={"status": "completed"},
        )
    )

    assert writer.enabled is False
    assert result == {"enabled": False, "wrote": False, "error": None}


def test_database_writer_requires_credentials_even_when_enabled():
    writer = DatabaseWriter(OrchestratorSettings(db_enabled=True))

    assert writer.enabled is False

