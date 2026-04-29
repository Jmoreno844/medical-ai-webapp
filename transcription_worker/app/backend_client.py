from __future__ import annotations

from typing import Any

import httpx

from app.settings import Settings


class BackendClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.backend_internal_base_url.rstrip("/")

    async def _auth_headers(self, url: str) -> dict[str, str]:
        if self._settings.is_local:
            return {}
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        token = id_token.fetch_id_token(google_requests.Request(), url)
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = await self._auth_headers(url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=headers, json=json)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

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
