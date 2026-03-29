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
    user_id: int, documento_id: int, minutes_ttl: int = 15
) -> Dict[str, Any]:
    """
    Claims for PATCH documento_by_function / notify/transcription-complete.

    Must match what documentos/api/ai.py expects: id_usuario, id_documento.
    """
    return {
        "id_usuario": user_id,
        "id_documento": documento_id,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
        "purpose": "transcription",
    }


def build_generation_callback_payload(
    user_id: int,
    documento_id: int,
    id_proceso: str,
    minutes_ttl: int = 30,
) -> Dict[str, Any]:
    """Claims for POST document/generation-chunk."""
    return {
        "id_usuario": user_id,
        "id_documento": documento_id,
        "id_proceso": id_proceso,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
        "purpose": "document_generation",
    }


def build_sse_token_payload(
    user_id: int,
    documento_id: int,
    minutes_ttl: int = 5,
    id_proceso: Optional[str] = None,
) -> Dict[str, Any]:
    """Claims for SSE stream handshake (with optional id_proceso for generation UI)."""
    payload: Dict[str, Any] = {
        "id_documento": documento_id,
        "id_usuario": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=minutes_ttl),
        "purpose": "sse_connection",
    }
    if id_proceso is not None:
        payload["id_proceso"] = id_proceso
    return payload
