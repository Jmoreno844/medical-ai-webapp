from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.observability import bind_log_context, log_event
from app.core.security import create_token
from app.core.service_jwt import issue_generation_callback_token
from app.db.models import User
from app.db.session import get_db_session
from app.domains.audit.service import actor_from_user, record_audit_event, record_security_event
from app.domains.auth.access import require_clinical_access
from app.domains.auth.service import get_current_user
from app.domains.documents.schemas import (
    ContextInputsOut,
    DocumentGenerationTaskPayload,
    DocumentGenerationWorkItemResponse,
    DocumentGenerationWorkflowRequest,
    DocumentGenerationWorkflowResponse,
    TranscriptionTurnWithId,
)
from app.domains.documents.service import (
    get_doctor_template_for_doctor,
    get_document_for_doctor,
    get_effective_template_content,
)
from app.domains.documents.sse_hub import get_processing_id, publish_document_event
from app.domains.documents.structured_template import default_clinical_template_out
from app.domains.documents.worker_auth import verify_document_generation_worker_request
from app.domains.transcription.service import (
    resolve_structured_transcription_turns_for_generation,
    resolve_transcription_content_for_generation,
)
from app.integrations.document_pipeline_tasks import (
    DocumentPipelineTaskConfigurationError,
    enqueue_document_pipeline_task,
    should_use_document_pipeline_cloud_tasks,
)
from app.integrations.http_json import post_json_async

logger = logging.getLogger(__name__)
router = APIRouter()


async def _post_document_worker_task_background(
    path: str,
    payload: dict,
    settings: Settings,
) -> None:
    if not settings.document_pipeline_worker_base_url:
        return
    url = f"{settings.document_pipeline_worker_base_url.rstrip('/')}{path}"
    try:
        with bind_log_context(
            process_id=payload.get("process_id"),
            document_id=payload.get("new_document_id"),
        ):
            await post_json_async(url, payload, timeout=900)
    except Exception:
        log_event(
            logger,
            logging.ERROR,
            "Local document pipeline worker dispatch failed",
            event="document_pipeline_worker_dispatch_failed",
            process_id=payload.get("process_id"),
            document_id=payload.get("new_document_id"),
        )
        document_id = payload.get("new_document_id")
        process_id = payload.get("process_id")
        if isinstance(document_id, int):
            await publish_document_event(
                document_id,
                "generation_error",
                {
                    "process_id": process_id,
                    "error": (
                        "No se pudo iniciar la generación del documento. "
                        "Reintente en unos momentos."
                    ),
                },
            )


@router.post(
    "/documents/generate",
    response_model=DocumentGenerationWorkflowResponse,
)
async def generate_document_endpoint(
    payload: DocumentGenerationWorkflowRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DocumentGenerationWorkflowResponse:
    require_clinical_access(user)
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
        await record_security_event(
            session,
            action="clinical.access_denied",
            result="denied",
            request=request,
            settings=settings,
            actor=actor_from_user(user),
            session_id=getattr(request.state, "auth_session_id", None),
            resource_type="document_generation",
            resource_id=payload.new_document_id,
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No tienes permiso para acceder a uno o más documentos requeridos",
        )
    transcription_turns = await resolve_structured_transcription_turns_for_generation(
        session,
        document_id=doc_transcription.id,
        doctor_id=user.id,
        fallback_markdown=doc_transcription.content_markdown,
    )
    if not transcription_turns:
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
        should_use_document_pipeline_cloud_tasks(settings)
        and not settings.document_pipeline_task_target_url
    ):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DOCUMENT_PIPELINE_TASK_TARGET_URL setting is not configured",
        )
    if (
        not should_use_document_pipeline_cloud_tasks(settings)
        and not settings.document_pipeline_worker_base_url
    ):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DOCUMENT_PIPELINE_WORKER_BASE_URL setting is not configured",
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
    await record_audit_event(
        session,
        action="document.ai_regeneration_started",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=doc_new.encounter_id,
        document_id=doc_new.id,
        resource_type="document_generation",
        resource_id=process_id,
    )

    await session.commit()

    try:
        if should_use_document_pipeline_cloud_tasks(settings):
            enqueue_document_pipeline_task(task_payload_dict, settings=settings)
        else:
            background_tasks.add_task(
                _post_document_worker_task_background,
                (
                    f"{settings.api_v1_prefix}/internal/document-pipeline/tasks/"
                    f"{process_id}"
                ),
                task_payload_dict,
                settings,
            )
    except DocumentPipelineTaskConfigurationError as exc:
        logger.error("Document pipeline task misconfigured: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to enqueue document pipeline task")
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
    "/internal/document-pipeline/work-items/{process_id}",
    response_model=DocumentGenerationWorkItemResponse,
)
async def get_document_pipeline_work_item(
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
    transcription_turns_raw = await resolve_structured_transcription_turns_for_generation(
        session,
        document_id=doc_transcription.id,
        doctor_id=payload.doctor_id,
        fallback_markdown=doc_transcription.content_markdown,
    )
    transcription_content = await resolve_transcription_content_for_generation(
        session,
        document_id=doc_transcription.id,
        doctor_id=payload.doctor_id,
        fallback_markdown=doc_transcription.content_markdown,
    )
    if not transcription_turns_raw or not template_content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Work item inválido")

    template_structured = default_clinical_template_out(
        template_name=doctor_template.name,
    )
    context_content = doc_context.content_markdown.strip() or "No se agregó contexto."
    context_inputs = ContextInputsOut(
        doctor_note_markdown=context_content,
        external_documents=[],
    )
    callback_token = issue_generation_callback_token(
        user_id=payload.doctor_id,
        document_id=doc_new.id,
        process_id=process_id,
        settings=settings,
    )
    transcription_turns = [
        TranscriptionTurnWithId(
            turn_id=int(turn["turn_id"]),
            speaker=str(turn["speaker"]),
            text=str(turn["text"]),
        )
        for turn in transcription_turns_raw
    ]
    return DocumentGenerationWorkItemResponse(
        process_id=process_id,
        doctor_id=payload.doctor_id,
        new_document_id=doc_new.id,
        context_document_id=doc_context.id,
        transcription_document_id=doc_transcription.id,
        doctor_template_id=doctor_template.id,
        encounter_id=doc_new.encounter_id,
        context_inputs=context_inputs,
        context_content=context_content,
        transcription_content=transcription_content,
        template_content=template_content,
        transcription_turns=transcription_turns,
        template=template_structured,
        callback_token=callback_token,
    )
