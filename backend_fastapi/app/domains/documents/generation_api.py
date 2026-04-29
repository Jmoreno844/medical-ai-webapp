from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import create_token
from app.core.service_jwt import issue_generation_callback_token
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.schemas import (
    DocumentGenerationTaskPayload,
    DocumentGenerationWorkItemResponse,
    DocumentGenerationWorkflowRequest,
    DocumentGenerationWorkflowResponse,
)
from app.domains.documents.service import (
    get_doctor_template_for_doctor,
    get_document_for_doctor,
    get_effective_template_content,
)
from app.domains.documents.sse_hub import get_processing_id, publish_document_event
from app.domains.documents.worker_auth import verify_document_generation_worker_request
from app.integrations.document_generation_tasks import (
    DocumentGenerationTaskConfigurationError,
    enqueue_document_generation_task,
    should_use_document_generation_cloud_tasks,
)
from app.integrations.http_json import post_json

logger = logging.getLogger(__name__)
router = APIRouter()


async def _post_document_worker_task_background(
    path: str,
    payload: dict,
    settings: Settings,
) -> None:
    if not settings.document_generation_worker_base_url:
        return
    url = f"{settings.document_generation_worker_base_url.rstrip('/')}{path}"
    try:
        await asyncio.to_thread(post_json, url, payload, timeout=5)
    except Exception:
        logger.exception(
            "Local document generation worker dispatch failed process_id=%s",
            payload.get("process_id"),
        )


@router.post(
    "/documents/generate",
    response_model=DocumentGenerationWorkflowResponse,
)
async def generate_document_endpoint(
    payload: DocumentGenerationWorkflowRequest,
    background_tasks: BackgroundTasks,
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
    if (
        should_use_document_generation_cloud_tasks(settings)
        and not settings.document_generation_task_target_url
    ):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DOCUMENT_GENERATION_TASK_TARGET_URL setting is not configured",
        )
    if (
        not should_use_document_generation_cloud_tasks(settings)
        and not settings.document_generation_worker_base_url
    ):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DOCUMENT_GENERATION_WORKER_BASE_URL setting is not configured",
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
    task_payload = DocumentGenerationTaskPayload(
        process_id=process_id,
        doctor_id=user.id,
        new_document_id=doc_new.id,
        context_document_id=doc_context.id,
        transcription_document_id=doc_transcription.id,
        doctor_template_id=doctor_template.id,
    )
    task_payload_dict = task_payload.model_dump()

    await session.commit()

    try:
        if should_use_document_generation_cloud_tasks(settings):
            enqueue_document_generation_task(task_payload_dict, settings=settings)
        else:
            background_tasks.add_task(
                _post_document_worker_task_background,
                (
                    f"{settings.api_v1_prefix}/internal/document-generation/tasks/"
                    f"{process_id}"
                ),
                task_payload_dict,
                settings,
            )
    except DocumentGenerationTaskConfigurationError as exc:
        logger.error("Document generation task misconfigured: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to enqueue document generation task")
        await publish_document_event(
            doc_new.id,
            "generation_error",
            {
                "process_id": process_id,
                "error": "Error al encolar generación de documento",
            },
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error al encolar generación de documento",
        ) from exc

    await publish_document_event(
        doc_new.id,
        "generation_chunk",
        {"process_id": process_id, "chunk": "Iniciando generación de documento..."},
    )

    return DocumentGenerationWorkflowResponse(
        success=True,
        process_id=process_id,
        sse_token=sse_token,
        new_document_id=doc_new.id,
        message="Generación de documento iniciada correctamente",
    )


@router.post(
    "/internal/document-generation/work-items/{process_id}",
    response_model=DocumentGenerationWorkItemResponse,
)
async def get_document_generation_work_item(
    process_id: str,
    payload: DocumentGenerationTaskPayload,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DocumentGenerationWorkItemResponse:
    verify_document_generation_worker_request(request, settings)
    if payload.process_id != process_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid processing ID")

    doc_context = await get_document_for_doctor(
        session,
        document_id=payload.context_document_id,
        doctor_id=payload.doctor_id,
    )
    doc_transcription = await get_document_for_doctor(
        session,
        document_id=payload.transcription_document_id,
        doctor_id=payload.doctor_id,
    )
    doc_new = await get_document_for_doctor(
        session,
        document_id=payload.new_document_id,
        doctor_id=payload.doctor_id,
    )
    if not doc_context or not doc_transcription or not doc_new:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    doctor_template = await get_doctor_template_for_doctor(
        session,
        template_id=payload.doctor_template_id,
        doctor_id=payload.doctor_id,
    )
    if not doctor_template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla no encontrada")

    template_content = get_effective_template_content(doctor_template)
    transcription_content = doc_transcription.content_markdown
    if not transcription_content.strip() or not template_content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Work item inválido")

    context_content = doc_context.content_markdown.strip() or "No se agregó contexto."
    callback_token = issue_generation_callback_token(
        user_id=payload.doctor_id,
        document_id=doc_new.id,
        process_id=process_id,
        settings=settings,
    )
    return DocumentGenerationWorkItemResponse(
        process_id=process_id,
        doctor_id=payload.doctor_id,
        new_document_id=doc_new.id,
        context_document_id=doc_context.id,
        transcription_document_id=doc_transcription.id,
        doctor_template_id=doctor_template.id,
        encounter_id=doc_new.encounter_id,
        context_content=context_content,
        transcription_content=transcription_content,
        template_content=template_content,
        callback_token=callback_token,
    )
