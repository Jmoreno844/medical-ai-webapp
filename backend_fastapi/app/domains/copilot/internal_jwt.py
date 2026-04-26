from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

settings = get_settings()

_bearer = HTTPBearer(auto_error=False)


def encode_copilot_internal_jwt(
    *,
    purpose: str,
    audience: str,
    issuer: str = "app-api-service",
    subject: str = "fastapi-copilot-broker",
    minutes_ttl: int = 5,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "purpose": purpose,
        "exp": datetime.now(UTC) + timedelta(minutes=minutes_ttl),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.copilot_service_shared_jwt, algorithm="HS256")


def decode_copilot_internal_jwt(*, token: str, audience: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.copilot_service_shared_jwt,
        algorithms=["HS256"],
        audience=audience,
    )


async def require_copilot_tools_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token interno invalido")
    try:
        payload = decode_copilot_internal_jwt(
            token=credentials.credentials,
            audience=settings.copilot_backend_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token interno invalido") from exc
    if payload.get("purpose") != "copilot_internal_tools":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token interno invalido")
    request.state.copilot_claims = payload
    return payload
