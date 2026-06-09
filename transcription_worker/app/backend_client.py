from __future__ import annotations

from typing import Any

from app.settings import Settings
from worker_runtime.backend_client import BaseBackendClient


class BackendClient(BaseBackendClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    async def get_section_work_item(self, section_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/internal/transcription/work-items/sections/{section_id}",
        )

    async def post_section_result(
        self,
        section_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self._request(
            "POST",
            f"/api/v1/internal/transcription/results/sections/{section_id}",
            json=payload,
        )
