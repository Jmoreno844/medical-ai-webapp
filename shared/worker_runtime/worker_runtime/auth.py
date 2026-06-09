from __future__ import annotations

import base64
import json

from fastapi import HTTPException, Request, status

from worker_runtime.settings import BaseWorkerSettings

_GOOGLE_TOKEN_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
_CLOUD_RUN_STRIPPED_SIGNATURE = "SIGNATURE_REMOVED_BY_GOOGLE"


def _cloud_tasks_bearer_token(request: Request) -> str | None:
    for header_name in ("authorization", "x-serverless-authorization"):
        header_value = request.headers.get(header_name, "")
        scheme, _, token = header_value.partition(" ")
        if token.strip() and scheme.lower() == "bearer":
            return token.strip()
    return None


def _decode_unverified_oidc_claims(token: str, *, audience: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT")

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))

    token_audience = payload.get("aud")
    if token_audience != audience:
        raise ValueError(f"Invalid audience: {token_audience!r}")

    issuer = payload.get("iss")
    if issuer not in _GOOGLE_TOKEN_ISSUERS:
        raise ValueError(f"Invalid issuer: {issuer!r}")

    return payload


def _decode_cloud_tasks_claims(token: str, *, audience: str) -> dict[str, object]:
    if _CLOUD_RUN_STRIPPED_SIGNATURE not in token:
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            return id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=audience,
            )
        except Exception:
            pass

    return _decode_unverified_oidc_claims(token, audience=audience)


def verify_cloud_tasks_request(
    request: Request,
    settings: BaseWorkerSettings,
) -> None:
    token = _cloud_tasks_bearer_token(request)
    if not token:
        if settings.is_local:
            return
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cloud Tasks auth required")

    try:
        payload = _decode_cloud_tasks_claims(token, audience=str(request.url))
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid Cloud Tasks token",
        ) from exc

    expected_email = (settings.cloud_tasks_invoker_service_account or "").strip()
    if expected_email and payload.get("email") != expected_email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid task invoker")
