from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import jwt
from django.conf import settings


def encode_copilot_internal_jwt(
    *,
    purpose: str,
    audience: str,
    issuer: str = "app-api-service",
    subject: str = "django-copilot-broker",
    minutes_ttl: int = 5,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "purpose": purpose,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.COPILOT_SERVICE_SHARED_JWT, algorithm="HS256")

