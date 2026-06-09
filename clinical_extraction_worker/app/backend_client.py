from __future__ import annotations

from typing import Any

from app.settings import Settings
from worker_runtime.backend_client import BaseBackendClient


class BackendClient(BaseBackendClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    async def fetch_work_item(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/internal/clinical-extraction/work-items/{session_id}",
        )

    async def post_result(
        self,
        session_id: str,
        *,
        callback_token: str,
        payload: dict[str, Any],
    ) -> None:
        await self.post_callback(
            f"/api/v1/internal/clinical-extraction/results/{session_id}",
            callback_token=callback_token,
            payload=payload,
        )
