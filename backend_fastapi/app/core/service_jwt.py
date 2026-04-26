from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.core.security import create_token, decode_token


def issue_transcription_callback_token(
    *,
    user_id: int,
    document_id: int,
    settings: Settings,
) -> str:
    token, _ = create_token(
        subject=str(user_id),
        purpose="transcription",
        audience=settings.callback_jwt_audience,
        expires_delta=timedelta(minutes=settings.transcription_callback_token_minutes),
        extra_claims={"user_id": user_id, "document_id": document_id},
        settings=settings,
    )
    return token


def issue_generation_callback_token(
    *,
    user_id: int,
    document_id: int,
    process_id: str,
    settings: Settings,
) -> str:
    token, _ = create_token(
        subject=str(user_id),
        purpose="document_generation",
        audience=settings.callback_jwt_audience,
        expires_delta=timedelta(minutes=settings.generation_callback_token_minutes),
        extra_claims={
            "user_id": user_id,
            "document_id": document_id,
            "process_id": process_id,
        },
        settings=settings,
    )
    return token


def extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return token.strip()


def decode_callback_token(
    request: Request,
    *,
    purpose: str,
    settings: Settings,
) -> dict[str, Any]:
    return decode_token(
        extract_bearer_token(request),
        audience=settings.callback_jwt_audience,
        purpose=purpose,
        settings=settings,
    )


def require_claim_int(payload: dict[str, Any], claim: str) -> int:
    try:
        return int(payload[claim])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Invalid {claim}") from exc
