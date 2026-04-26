from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.service_jwt import issue_transcription_callback_token
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import get_document_for_doctor, get_encounter_for_doctor
from app.domains.transcription.schemas import TranscriptionRequest, TranscriptionResponse
from app.integrations.http_json import JsonHttpError, post_json
from app.integrations.transcription_tasks import (
    TranscriptionTaskConfigurationError,
    enqueue_transcription_task,
    should_use_cloud_tasks,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/transcription/start", response_model=TranscriptionResponse)
async def start_transcription(
    payload: TranscriptionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResponse:
    encounter = await get_encounter_for_doctor(
        session,
        encounter_id=payload.encounter_id,
        doctor_id=user.id,
    )
    if not encounter:
        return TranscriptionResponse(
            success=False,
            error="Not authorized for this encounter",
        )
    if not encounter.audio_file_name:
        return TranscriptionResponse(
            success=False,
            error="No audio file associated with this encounter",
        )
    if encounter.audio_expires_at:
        now = datetime.now(encounter.audio_expires_at.tzinfo)
        if encounter.audio_expires_at <= now:
            return TranscriptionResponse(success=False, error="Audio file has expired")

    document = await get_document_for_doctor(
        session,
        document_id=payload.document_id,
        doctor_id=user.id,
    )
    if not document or document.encounter_id != encounter.id:
        return TranscriptionResponse(
            success=False,
            error="No tienes permiso para acceder a este documento",
        )
    if not settings.gcs_bucket_name:
        return TranscriptionResponse(success=False, error="GCS_BUCKET_NAME is not configured")
    if not settings.transcription_cloud_function_url:
        return TranscriptionResponse(
            success=False,
            error="TRANSCRIPTION_CLOUD_FUNCTION_URL is not configured",
        )

    auth_token = issue_transcription_callback_token(
        user_id=user.id,
        document_id=document.id,
        settings=settings,
    )
    cloud_function_payload = {
        "document_id": document.id,
        "audio_uri": f"gs://{settings.gcs_bucket_name}/{encounter.audio_file_name}",
        "auth_token": auth_token,
    }

    try:
        if should_use_cloud_tasks(settings):
            task_name = enqueue_transcription_task(
                cloud_function_payload,
                settings=settings,
            )
            logger.info(
                "Transcription task queued for document %s with task %s",
                document.id,
                task_name,
            )
            return TranscriptionResponse(
                success=True,
                message="Transcription queued successfully",
            )

        await asyncio.to_thread(
            post_json,
            settings.transcription_cloud_function_url,
            cloud_function_payload,
            timeout=30,
        )
        return TranscriptionResponse(
            success=True,
            message="Transcription initiated successfully",
        )
    except TranscriptionTaskConfigurationError as exc:
        logger.error("Cloud Tasks transcription misconfigured: %s", exc)
        return TranscriptionResponse(success=False, error=str(exc))
    except JsonHttpError as exc:
        logger.error("Error calling transcription cloud function: %s", exc)
        return TranscriptionResponse(
            success=False,
            error=f"Failed to initiate transcription: {exc}",
        )
