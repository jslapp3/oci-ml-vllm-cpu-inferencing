"""Optional Autonomous Database write path for inference logging."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from .config import OrchestratorSettings, get_settings


class DatabaseWriter:
    def __init__(self, settings: Optional[OrchestratorSettings] = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.db_enabled
            and self.settings.oracle_user
            and self.settings.oracle_password
            and self.settings.oracle_dsn
        )

    async def write_inference_run(
        self,
        run_id: str,
        request_payload: Dict[str, Any],
        response_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "wrote": False, "error": None}

        try:
            await asyncio.to_thread(self._write_sync, run_id, request_payload, response_payload)
            return {"enabled": True, "wrote": True, "error": None}
        except Exception as exc:
            return {"enabled": True, "wrote": False, "error": f"{type(exc).__name__}: {exc}"}

    def _write_sync(
        self,
        run_id: str,
        request_payload: Dict[str, Any],
        response_payload: Dict[str, Any],
    ) -> None:
        import oracledb

        with oracledb.connect(
            user=self.settings.oracle_user,
            password=self.settings.oracle_password,
            dsn=self.settings.oracle_dsn,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into inference_runs (
                        run_id,
                        entity_id,
                        status,
                        request_payload,
                        ml_output,
                        llm_output
                    ) values (
                        :run_id,
                        :entity_id,
                        :status,
                        :request_payload,
                        :ml_output,
                        :llm_output
                    )
                    """,
                    {
                        "run_id": run_id,
                        "entity_id": request_payload.get("series_id", "default"),
                        "status": response_payload.get("status", "completed"),
                        "request_payload": json.dumps(request_payload, default=str),
                        "ml_output": json.dumps(response_payload.get("ml_output", {}), default=str),
                        "llm_output": json.dumps(
                            {
                                "explanation": response_payload.get("explanation", {}),
                                "recommendations": response_payload.get("recommendations", {}),
                                "extracted_features": response_payload.get("extracted_features", {}),
                            },
                            default=str,
                        ),
                    },
                )
            connection.commit()

