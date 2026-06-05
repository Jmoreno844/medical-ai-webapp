from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx


class JsonHttpError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise JsonHttpError(
            f"HTTP {exc.code} from {url}: {details}",
            status_code=exc.code,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise JsonHttpError(f"Error calling {url}: {exc}") from exc


async def post_json_async(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
    except httpx.HTTPStatusError as exc:
        details = exc.response.text
        raise JsonHttpError(
            f"HTTP {exc.response.status_code} from {url}: {details}",
            status_code=exc.response.status_code,
        ) from exc
    except httpx.HTTPError as exc:
        raise JsonHttpError(f"Error calling {url}: {exc}") from exc
