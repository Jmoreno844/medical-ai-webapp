from __future__ import annotations

import base64
import json

import pytest
from fastapi import Request

from worker_runtime.auth import verify_cloud_tasks_request
from worker_runtime.settings import BaseWorkerSettings


def _jwt_payload(audience: str) -> str:
    payload = {
        "aud": audience,
        "iss": "https://accounts.google.com",
        "email": "tasks@example.com",
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.SIGNATURE_REMOVED_BY_GOOGLE"


@pytest.mark.asyncio
async def test_verify_cloud_tasks_request_allows_local_without_token() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/task",
            "headers": [],
            "scheme": "https",
            "server": ("example.com", 443),
        }
    )
    settings = BaseWorkerSettings(_env_file=None, ENVIRONMENT="local")

    verify_cloud_tasks_request(request, settings)


@pytest.mark.asyncio
async def test_verify_cloud_tasks_request_accepts_stripped_signature_token() -> None:
    url = "https://example.com/internal/task"
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/task",
            "headers": [(b"authorization", f"Bearer {_jwt_payload(url)}".encode())],
            "scheme": "https",
            "server": ("example.com", 443),
        }
    )
    request._url = url  # type: ignore[attr-defined]
    settings = BaseWorkerSettings(
        _env_file=None,
        ENVIRONMENT="production",
        CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT="tasks@example.com",
    )

    verify_cloud_tasks_request(request, settings)
