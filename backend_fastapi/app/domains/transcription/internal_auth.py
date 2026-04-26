from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import Settings


def _is_local_environment(settings: Settings) -> bool:
    return settings.environment.strip().lower() in {"local", "dev", "develop", "test"}


def verify_cloud_tasks_request(request: Request, settings: Settings) -> None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if not token.strip():
        if _is_local_environment(settings):
            return
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cloud Tasks auth required")
    if scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid auth scheme")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        payload = id_token.verify_oauth2_token(
            token.strip(),
            google_requests.Request(),
            audience=str(request.url),
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid Cloud Tasks token",
        ) from exc

    expected_email = (settings.cloud_tasks_invoker_service_account or "").strip()
    if expected_email and payload.get("email") != expected_email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid task invoker")
