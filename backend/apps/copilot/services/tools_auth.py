from __future__ import annotations

from typing import Any, Optional

import jwt
from django.conf import settings
from ninja.security import HttpBearer


class CopilotToolsJWTAuth(HttpBearer):
    """Validate short-lived internal tokens sent by the copilot agent tools client."""

    def authenticate(self, _request, token: str) -> Optional[dict[str, Any]]:
        if not token:
            return None

        try:
            payload = jwt.decode(
                token,
                settings.COPILOT_SERVICE_SHARED_JWT,
                algorithms=["HS256"],
                audience=settings.COPILOT_BACKEND_AUDIENCE,
            )
        except jwt.PyJWTError:
            return None

        if payload.get("purpose") != "copilot_internal_tools":
            return None

        return payload
