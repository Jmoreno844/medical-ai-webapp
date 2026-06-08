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

    async def fetch_work_item(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        path = f"/api/v1/internal/clinical-extraction/work-items/{session_id}"
        url = f"{self._base_url}{path}"
        headers = await self._auth_headers(url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def post_result(
        self,
        session_id: str,
        *,
        callback_token: str,
        payload: dict[str, Any],
    ) -> None:
        url = f"{self._base_url}/api/v1/internal/clinical-extraction/results/{session_id}"
        headers = {"Authorization": f"Bearer {callback_token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
