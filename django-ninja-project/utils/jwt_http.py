"""Decode Bearer JWT when Ninja does not populate auth (e.g. some CSRF/callback paths)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import jwt
from django.http import HttpRequest

from utils.jwt_settings import get_jwt_signing_key

logger = logging.getLogger(__name__)


def resolve_bearer_jwt_payload(
    request: HttpRequest, auth: Optional[dict]
) -> Optional[dict]:
    """
    Return decoded JWT claims from auth or from Authorization: Bearer header.
    """
    if auth is not None:
        return auth
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        return jwt.decode(token, get_jwt_signing_key(), algorithms=["HS256"])
    except jwt.PyJWTError as e:
        logger.warning("Bearer JWT decode failed: %s", type(e).__name__)
        return None
