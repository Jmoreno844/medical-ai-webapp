from __future__ import annotations

from typing import Any

import httpx

from worker_runtime.settings import BaseWorkerSettings


class BaseBackendClient:
    def __init__(self, settings: BaseWorkerSettings) -> None:
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
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = await self._auth_headers(url)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, headers=headers, json=json)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

    async def post_callback(
        self,
        path: str,
        *,
        callback_token: str,
        payload: dict[str, Any],
        timeout: float = 30.0,
    ) -> None:
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {callback_token}"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
