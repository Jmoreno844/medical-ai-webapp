from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import create_token, decode_token
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import get_document_for_doctor
from app.domains.documents.sse_hub import subscribe, unsubscribe
from app.domains.documents.sse_schemas import SSETokenResponse

router = APIRouter()


@router.post(
    "/documents/{document_id}/sse-token",
    response_model=SSETokenResponse,
)
async def generate_sse_token(
    document_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SSETokenResponse:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not document:
        return SSETokenResponse(
            success=False,
            error="Documento no encontrado o sin permiso",
        )

    token, _ = create_token(
        subject=str(user.id),
        purpose="sse_connection",
        audience=settings.sse_jwt_audience,
        expires_delta=timedelta(minutes=settings.sse_token_minutes),
        extra_claims={"user_id": user.id, "document_id": document_id},
        settings=settings,
    )
    return SSETokenResponse(success=True, token=token)


@router.get("/sse/documents/{document_id}/{token}")
async def subscribe_to_document_updates(
    document_id: int,
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    payload = decode_token(
        token,
        audience=settings.sse_jwt_audience,
        purpose="sse_connection",
        settings=settings,
    )
    if int(payload.get("document_id", 0)) != document_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token document mismatch")

    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=int(payload["user_id"]),
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    async def event_stream():
        queue = await subscribe(document_id)
        connected = {"event": "connected", "document_id": document_id}
        yield f"data: {json.dumps(connected)}\n\n"
        try:
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            await unsubscribe(document_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

