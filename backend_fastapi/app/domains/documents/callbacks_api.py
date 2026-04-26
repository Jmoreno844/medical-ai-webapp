from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.schemas import SuccessResponse
from app.core.service_jwt import (
    decode_callback_token,
    require_claim_int,
)
from app.db.session import get_db_session
from app.domains.documents.content import set_document_content_fields
from app.domains.documents.schemas import (
    DocumentContentUpdate,
    GenerationChunkIn,
    TranscriptionNotificationIn,
)
from app.domains.documents.service import get_document_for_doctor
from app.domains.documents.sse_hub import publish_document_event

logger = logging.getLogger(__name__)
router = APIRouter()


@router.patch("/documents/by-function/{document_id}", response_model=SuccessResponse)
async def update_document_by_function(
    document_id: int,
    payload: DocumentContentUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse:
    token_payload = decode_callback_token(
        request,
        purpose="transcription",
        settings=settings,
    )
    doctor_id = require_claim_int(token_payload, "user_id")
    token_document_id = require_claim_int(token_payload, "document_id")
    if token_document_id != document_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid document ID")

    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=doctor_id,
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    preferred_source = (
        "markdown"
        if payload.content_markdown is not None or payload.content is not None
        else "json"
    )
    set_document_content_fields(
        document,
        content_markdown=payload.content_markdown or payload.content or "",
        content_json=payload.content_json,
        preferred_source=preferred_source,
    )
    await session.commit()
    await publish_document_event(document_id, "transcription_complete")
    return SuccessResponse(
        success=True,
        message=f"Documento {document_id} actualizado exitosamente",
    )


@router.post("/transcription/notify-complete", response_model=SuccessResponse)
async def transcription_complete_notification(
    payload: TranscriptionNotificationIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse:
    token_payload = decode_callback_token(
        request,
        purpose="transcription",
        settings=settings,
    )
    doctor_id = require_claim_int(token_payload, "user_id")
    token_document_id = require_claim_int(token_payload, "document_id")
    if token_document_id != payload.document_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid document ID")

    document = await get_document_for_doctor(
        session,
        document_id=payload.document_id,
        doctor_id=doctor_id,
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    await session.refresh(document, attribute_names=["encounter"])
    if not document.encounter.has_been_transcribed:
        document.encounter.has_been_transcribed = True
    await session.commit()
    await publish_document_event(payload.document_id, "transcription_complete")
    return SuccessResponse(
        success=True,
        message=f"Notificación enviada para documento {payload.document_id}",
    )


@router.post("/documents/generation-chunk", response_model=SuccessResponse)
async def receive_generation_chunk(
    payload: GenerationChunkIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse:
    token_payload = decode_callback_token(
        request,
        purpose="document_generation",
        settings=settings,
    )
    doctor_id = require_claim_int(token_payload, "user_id")
    token_document_id = require_claim_int(token_payload, "document_id")
    token_process_id = token_payload.get("process_id")
    if token_document_id != payload.document_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid document ID")
    if token_process_id != payload.process_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid processing ID")

    document = await get_document_for_doctor(
        session,
        document_id=payload.document_id,
        doctor_id=doctor_id,
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    if payload.is_error:
        await publish_document_event(
            payload.document_id,
            "generation_error",
            {
                "process_id": payload.process_id,
                "error": payload.error or "Error en la generación",
            },
        )
        return SuccessResponse(
            success=False,
            error=payload.error or "Error en la generación",
        )

    if payload.is_complete:
        if payload.chunk:
            set_document_content_fields(
                document,
                content_markdown=payload.chunk,
                preferred_source="markdown",
            )
            await session.commit()
        await publish_document_event(
            payload.document_id,
            "generation_complete",
            {"process_id": payload.process_id, "chunk": payload.chunk},
        )
        return SuccessResponse(
            success=True,
            message=f"Generación completada para documento {payload.document_id}",
        )

    await publish_document_event(
        payload.document_id,
        "generation_chunk",
        {"process_id": payload.process_id, "chunk": payload.chunk or ""},
    )
    return SuccessResponse(
        success=True,
        message=f"Chunk received for document {payload.document_id}",
    )
