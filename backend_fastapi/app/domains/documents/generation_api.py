from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import create_token
from app.core.service_jwt import issue_generation_callback_token
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.generation_runner import start_document_generation_task
from app.domains.documents.schemas import (
    DocumentGenerationWorkflowRequest,
    DocumentGenerationWorkflowResponse,
)
from app.domains.documents.service import (
    get_doctor_template_for_doctor,
    get_document_for_doctor,
    get_effective_template_content,
)
from app.domains.documents.sse_hub import get_processing_id, publish_document_event
from app.integrations.http_json import JsonHttpError, post_json

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/documents/generate",
    response_model=DocumentGenerationWorkflowResponse,
)
async def generate_document_workflow(
    payload: DocumentGenerationWorkflowRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DocumentGenerationWorkflowResponse:
    doc_context = await get_document_for_doctor(
        session,
        document_id=payload.context_document_id,
        doctor_id=user.id,
    )
    doc_transcription = await get_document_for_doctor(
        session,
        document_id=payload.transcription_document_id,
        doctor_id=user.id,
    )
    doc_new = await get_document_for_doctor(
        session,
        document_id=payload.new_document_id,
        doctor_id=user.id,
    )
    if not doc_context or not doc_transcription or not doc_new:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No tienes permiso para acceder a uno o más documentos requeridos",
        )
    if not doc_transcription.content_markdown.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El documento de transcripción está vacío. Se requiere contenido para generar el documento.",
        )

    doctor_template = await get_doctor_template_for_doctor(
        session,
        template_id=payload.doctor_template_id,
        doctor_id=user.id,
    )
    if not doctor_template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla de doctor no encontrada")

    template_content = get_effective_template_content(doctor_template)
    if not template_content or not template_content.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La plantilla seleccionada está vacía. Se requiere contenido para generar el documento.",
        )
    if not settings.generate_document_cloud_function_url:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "GENERATE_DOCUMENT_CLOUD_FUNCTION_URL setting is not configured",
        )

    doc_new.doctor_template_id = doctor_template.id
    process_id = get_processing_id(doc_new.id)
    sse_token, _ = create_token(
        subject=str(user.id),
        purpose="sse_connection",
        audience=settings.sse_jwt_audience,
        expires_delta=timedelta(minutes=15),
        extra_claims={
            "user_id": user.id,
            "document_id": doc_new.id,
            "process_id": process_id,
        },
        settings=settings,
    )
    callback_token = issue_generation_callback_token(
        user_id=user.id,
        document_id=doc_new.id,
        process_id=process_id,
        settings=settings,
    )

    request_body = {
        "new_document_id": doc_new.id,
        "process_id": process_id,
        "context_document": {
            "id": doc_context.id,
            "content": doc_context.content_markdown,
        },
        "transcription_document": {
            "id": doc_transcription.id,
            "content": doc_transcription.content_markdown,
        },
        "template": {
            "id": doctor_template.id,
            "content": template_content,
        },
        "auth_token": callback_token,
        "validate_only": True,
    }

    try:
        validation_data = await asyncio.to_thread(
            post_json,
            settings.generate_document_cloud_function_url,
            request_body,
            timeout=10,
        )
    except JsonHttpError as exc:
        logger.error("Error during generation validation request: %s", exc)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Error de conexión con el servicio: {exc}",
        ) from exc

    if not validation_data.get("success", False):
        error_msg = validation_data.get("error", "Error desconocido en la validación")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Error en los parámetros: {error_msg}",
        )

    await publish_document_event(
        doc_new.id,
        "generation_chunk",
        {"process_id": process_id, "chunk": "Iniciando generación de documento..."},
    )

    request_body["validate_only"] = False
    await session.commit()
    await start_document_generation_task(
        url=settings.generate_document_cloud_function_url,
        request_body=request_body,
        document_id=doc_new.id,
        process_id=process_id,
    )

    return DocumentGenerationWorkflowResponse(
        success=True,
        process_id=process_id,
        sse_token=sse_token,
        new_document_id=doc_new.id,
        message="Generación de documento iniciada correctamente",
    )
