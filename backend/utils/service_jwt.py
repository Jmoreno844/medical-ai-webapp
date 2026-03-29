"""
JWT payloads issued for Cloud Function callbacks and short-lived SSE tokens.

All service tokens verified by utils.auth.JWTAuth must use the claims documented
in documentation/jwt_and_auth_contracts.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt

from utils.jwt_settings import get_jwt_signing_key


def encode_service_jwt(payload: Dict[str, Any], algorithm: str = "HS256") -> str:
    """Sign a payload for Cloud Function or SSE callbacks."""
    return jwt.encode(payload, get_jwt_signing_key(), algorithm=algorithm)


def build_transcription_callback_payload(
    user_id: int, document_id: int, minutes_ttl: int = 15
) -> Dict[str, Any]:
    """Claims for PATCH documents/by-function / transcription notify."""
    return {
        "user_id": user_id,
        "document_id": document_id,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
        "purpose": "transcription",
    }


def build_generation_callback_payload(
    user_id: int,
    document_id: int,
    process_id: str,
    minutes_ttl: int = 30,
) -> Dict[str, Any]:
    """Claims for POST documents/generation-chunk."""
    return {
        "user_id": user_id,
        "document_id": document_id,
        "process_id": process_id,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
        "purpose": "document_generation",
    }


def build_sse_token_payload(
    user_id: int,
    document_id: int,
    minutes_ttl: int = 5,
    process_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Claims for SSE stream handshake (optional process_id for generation UI)."""
    payload: Dict[str, Any] = {
        "document_id": document_id,
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
        "purpose": "sse_connection",
    }
    if process_id is not None:
        payload["process_id"] = process_id
    return payload
