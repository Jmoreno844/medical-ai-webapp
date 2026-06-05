from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import Settings


def _is_local_environment(settings: Settings) -> bool:
    return settings.environment.strip().lower() in {"local", "dev", "develop", "test"}


def verify_document_generation_worker_request(
    request: Request,
    settings: Settings,
) -> dict[str, object] | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if not token.strip():
        if _is_local_environment(settings):
            return None
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Worker auth required")
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
            "Invalid worker token",
        ) from exc

    expected_email = (settings.document_generation_worker_service_account or "").strip()
    if expected_email and payload.get("email") != expected_email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid worker invoker")
    return payload
