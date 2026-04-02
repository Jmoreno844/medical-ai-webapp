from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt

from app.config import Settings


class CopilotBackendToolsError(Exception):
    pass


class CopilotBackendToolsClient:
    """Bounded tools client used by the agent runtime against Django."""

    def __init__(
        self,
        *,
        settings: Settings,
        run_id: str,
        thread_id: str,
        encounter_id: str,
        user_id: str,
    ) -> None:
        self._settings = settings
        self._run_id = run_id
        self._thread_id = thread_id
        self._encounter_id = encounter_id
        self._user_id = user_id
        self._base_url = settings.backend_internal_base_url.rstrip("/")

    def list_open_documents(self, workspace_index: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/open-documents",
            {
                **self._base_payload(),
                "workspace_index": workspace_index,
            },
        )

    def list_encounter_documents(self) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/encounter-documents",
            self._base_payload(),
        )

    def read_document_summary(self, document_id: str) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/read-document-summary",
            {
                **self._base_payload(),
                "document_id": int(document_id),
            },
        )

    def read_document_span(
        self,
        document_id: str,
        *,
        exact_text: str | None = None,
        prefix_text: str | None = None,
        suffix_text: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        max_chars: int = 600,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self._base_payload(),
            "document_id": int(document_id),
            "max_chars": max_chars,
        }
        if exact_text is not None:
            payload["exact_text"] = exact_text
        if prefix_text is not None:
            payload["prefix_text"] = prefix_text
        if suffix_text is not None:
            payload["suffix_text"] = suffix_text
        if start_offset is not None:
            payload["start_offset"] = start_offset
        if end_offset is not None:
            payload["end_offset"] = end_offset

        return self._request("/api/internal/copilot/tools/read-document-span", payload)

    def search_documents(
        self,
        *,
        query: str,
        max_results: int = 3,
        allowed_document_types: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/search-documents",
            {
                **self._base_payload(),
                "query": query,
                "max_results": max_results,
                "allowed_document_types": allowed_document_types or [],
            },
        )

    def read_patch_history(self, document_id: str, *, limit: int = 5) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/read-patch-history",
            {
                **self._base_payload(),
                "document_id": int(document_id),
                "limit": limit,
            },
        )

    def read_encounter_context(self) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/read-encounter-context",
            self._base_payload(),
        )

    def build_context_view(
        self,
        *,
        active_document_id: str | None = None,
        include_document_ids: list[str] | None = None,
        include_manual_context: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "/api/internal/copilot/tools/build-context-view",
            {
                **self._base_payload(),
                "active_document_id": int(active_document_id)
                if active_document_id
                else None,
                "include_document_ids": [int(document_id) for document_id in include_document_ids or []],
                "include_manual_context": include_manual_context,
            },
        )

    def _base_payload(self) -> dict[str, Any]:
        return {
            "run_id": self._run_id,
            "thread_id": self._thread_id,
            "encounter_id": int(self._encounter_id),
            "user_id": int(self._user_id),
        }

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._build_token()}"}

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self._settings.backend_internal_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise CopilotBackendToolsError(str(error)) from error

        return response.json()

    def _build_token(self) -> str:
        payload = {
            "iss": "copilot-agent-service",
            "sub": "copilot-agent-tools",
            "aud": self._settings.backend_audience,
            "purpose": "copilot_internal_tools",
            "run_id": self._run_id,
            "thread_id": self._thread_id,
            "encounter_id": self._encounter_id,
            "user_id": self._user_id,
            "exp": datetime.utcnow() + timedelta(minutes=5),
        }
        return jwt.encode(
            payload,
            self._settings.service_shared_jwt,
            algorithm="HS256",
        )
