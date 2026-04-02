from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

bearer_scheme = HTTPBearer(auto_error=True)


def require_internal_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    settings = get_settings()

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.service_shared_jwt,
            algorithms=["HS256"],
            audience=settings.allowed_audience,
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service token",
        ) from error

    if payload.get("purpose") != "copilot_internal_broker":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service token purpose",
        )

    return payload
