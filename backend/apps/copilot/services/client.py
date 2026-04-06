from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from apps.copilot.services.internal_jwt import encode_copilot_internal_jwt

logger = logging.getLogger(__name__)


class CopilotServiceError(Exception):
    """Raised when the copilot agent service returns an error or is unreachable.

    ``status_code`` is set when the agent returned an HTTP error response (e.g.
    409 Conflict).  It is None for network-level failures.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CopilotAgentClient:
    def __init__(self) -> None:
        self.base_url = settings.COPILOT_AGENT_BASE_URL.rstrip("/")
        # Edit runs can spend most of their wall time in Vertex drafting. Keep a
        # safety floor here so Django does not return a false 502 while the agent
        # is still finishing a valid reviewable proposal.
        self.timeout = max(60.0, float(settings.COPILOT_AGENT_TIMEOUT_SECONDS))

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/internal/copilot/runs", json=payload)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/internal/copilot/runs/{run_id}")

    def resume_run(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/internal/copilot/runs/{run_id}/resume",
            json=payload,
        )
        return response["run"]

    def list_run_events(
        self, run_id: str, *, after_sequence: int = 0
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/internal/copilot/runs/{run_id}/events",
            params={"after_sequence": after_sequence},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = encode_copilot_internal_jwt(
            purpose="copilot_internal_broker",
            audience=settings.COPILOT_AGENT_AUDIENCE,
        )
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            status_code = (
                error.response.status_code if error.response is not None else None
            )
            logger.error(
                "Copilot agent HTTP error: %s (status=%s)", error, status_code
            )
            raise CopilotServiceError(str(error), status_code=status_code) from error
        except requests.RequestException as error:
            logger.error("Copilot agent request failed: %s", error)
            raise CopilotServiceError(str(error)) from error

        return response.json()
