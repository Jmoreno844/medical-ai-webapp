from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.service_jwt import decode_callback_token, require_claim_int
from app.db.session import get_db_session
from app.domains.clinical_extraction.schemas import (
    ClinicalExtractionResultRequest,
    ClinicalExtractionWorkItemResponse,
)
from app.domains.clinical_extraction.service import (
    apply_clinical_extraction_result,
    get_clinical_extraction_work_item,
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
