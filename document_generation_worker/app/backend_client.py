from __future__ import annotations

from typing import Any

from app.settings import Settings
from worker_runtime.backend_client import BaseBackendClient


class BackendClient(BaseBackendClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    async def fetch_work_item(
        self,
        process_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/v1/internal/document-generation/work-items/{process_id}",
            json=payload,
        )

    async def post_generation_chunk(
        self,
        *,
        callback_token: str,
        payload: dict[str, Any],
    ) -> None:
        await self.post_callback(
            "/api/v1/documents/generation-chunk",
            callback_token=callback_token,
            payload=payload,
        )
