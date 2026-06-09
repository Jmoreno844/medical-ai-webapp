from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.environment import is_local_environment
from app.core.service_jwt import decode_callback_token, require_claim_int
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.access import require_clinical_access
from app.domains.auth.service import get_current_user
from app.domains.clinical_extraction.debug_controller import (
    run_debug_clinical_extraction,
)
from app.domains.clinical_extraction.schemas import (
    ClinicalExtractionResultRequest,
    ClinicalExtractionWorkItemResponse,
    DebugClinicalExtractionRequest,
    DebugClinicalExtractionResponse,
    DebugClinicalExtractionSessionTranscriptResponse,
)
from app.domains.clinical_extraction.service import (
    apply_clinical_extraction_result,
    get_clinical_extraction_work_item,
    get_debug_transcript_session,
)
from app.domains.clinical_extraction.worker_auth import (
    verify_clinical_extraction_worker_request,
)

router = APIRouter()


@router.get(
    "/internal/clinical-extraction/work-items/{session_id}",
    response_model=ClinicalExtractionWorkItemResponse,
)
async def get_worker_clinical_extraction_work_item(
    session_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ClinicalExtractionWorkItemResponse:
    verify_clinical_extraction_worker_request(request, settings)
    work_item = await get_clinical_extraction_work_item(
        session,
        session_id=session_id,
        settings=settings,
    )
    if not work_item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extracción no encontrada")
    return work_item


@router.post("/internal/clinical-extraction/results/{session_id}")
async def receive_clinical_extraction_result(
    session_id: str,
    payload: ClinicalExtractionResultRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    token_payload = decode_callback_token(
        request,
        purpose="clinical_extraction",
        settings=settings,
    )
    token_session_id = str(token_payload.get("session_id") or "")
    if token_session_id != session_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid session_id")
    token_encounter_id = require_claim_int(token_payload, "encounter_id")
    token_document_id = require_claim_int(token_payload, "document_id")

    extraction = await apply_clinical_extraction_result(
        session,
        session_id=session_id,
        status=payload.status,
        facts=payload.facts,
        raw_model_output=payload.raw_model_output,
        extraction_model=payload.extraction_model,
        grounding_stats=payload.grounding_stats,
        error_code=payload.error_code,
        latency_ms=payload.latency_ms,
    )
    if not extraction:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extracción no encontrada")
    if (
        extraction.encounter_id != token_encounter_id
        or extraction.document_id != token_document_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid callback claims")
    return {"success": True}


@router.get(
    "/clinical-extraction/debug/sessions/{session_id}/transcript",
    response_model=DebugClinicalExtractionSessionTranscriptResponse,
)
async def get_debug_session_transcript(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DebugClinicalExtractionSessionTranscriptResponse:
    require_clinical_access(user)
    if not is_local_environment(settings):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    recording_session = await get_debug_transcript_session(
        session,
        session_id=session_id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")

    return DebugClinicalExtractionSessionTranscriptResponse(
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        doctor_id=recording_session.doctor_id,
        status=recording_session.status,
        transcript_json=recording_session.transcript_json,
    )


@router.post(
    "/clinical-extraction/debug/extract",
    response_model=DebugClinicalExtractionResponse,
)
async def debug_clinical_extraction(
    payload: DebugClinicalExtractionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DebugClinicalExtractionResponse:
    require_clinical_access(user)
    if not is_local_environment(settings):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return await run_debug_clinical_extraction(
        payload=payload,
        db_session=session,
        settings=settings,
    )
