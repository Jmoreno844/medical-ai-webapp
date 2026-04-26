from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import get_settings
from app.domains.copilot.internal_jwt import encode_copilot_internal_jwt

logger = logging.getLogger(__name__)
settings = get_settings()


class CopilotServiceError(Exception):
    """Raised when the copilot agent service returns an error or is unreachable.

    ``status_code`` is set when the agent returned an HTTP error response (e.g.
    409 Conflict). It is None for network-level failures.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CopilotAgentClient:
    def __init__(self) -> None:
        self.base_url = settings.copilot_agent_base_url.rstrip("/")
        # Edit runs can spend most of their wall time in Vertex drafting. Keep a
        # safety floor here so FastAPI does not return a false 502 while the agent
        # is still finishing a valid reviewable proposal.
        self.timeout = max(60.0, float(settings.copilot_agent_timeout_seconds))

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/internal/copilot/runs", json_payload=payload)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/internal/copilot/runs/{run_id}")

    def resume_run(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/internal/copilot/runs/{run_id}/resume",
            json_payload=payload,
        )
        return response["run"]

    def list_run_events(self, run_id: str, *, after_sequence: int = 0) -> dict[str, Any]:
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
        json_payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = encode_copilot_internal_jwt(
            purpose="copilot_internal_broker",
            audience=settings.copilot_agent_audience,
        )
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        body = None
        if json_payload is not None:
            body = json.dumps(json_payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            logger.error("Copilot agent HTTP error: %s (status=%s)", error, error.code)
            raise CopilotServiceError(str(error), status_code=error.code) from error
        except urllib.error.URLError as error:
            logger.error("Copilot agent request failed: %s", error)
            raise CopilotServiceError(str(error)) from error

        return json.loads(response_body or "{}")
