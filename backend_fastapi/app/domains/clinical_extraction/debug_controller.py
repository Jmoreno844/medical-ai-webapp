from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domains.clinical_extraction.debug_mentions import (
    process_debug_clinical_mentions,
)
from app.domains.clinical_extraction.schemas import (
    DebugClinicalExtractionRequest,
    DebugClinicalExtractionResponse,
)
from app.domains.clinical_extraction.service import (
    _transcript_language,
    build_debug_recording_session_context,
    build_extraction_chunks_from_transcript,
    get_debug_transcript_session,
)

logger = logging.getLogger(__name__)

DEFAULT_DEBUG_CLINICAL_EXTRACTION_TIMEOUT_SECONDS = 600.0


def debug_clinical_extraction_timeout_seconds() -> float:
    raw = os.environ.get(
        "CLINICAL_EXTRACTION_DEBUG_TIMEOUT_SECONDS",
        str(int(DEFAULT_DEBUG_CLINICAL_EXTRACTION_TIMEOUT_SECONDS)),
    ).strip()
    try:
        timeout = float(raw)
    except ValueError:
        timeout = DEFAULT_DEBUG_CLINICAL_EXTRACTION_TIMEOUT_SECONDS
    return max(timeout, 30.0)


def build_debug_clinical_extraction_http_timeout() -> httpx.Timeout:
    read_timeout = debug_clinical_extraction_timeout_seconds()
    return httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)

WorkerCaller = Callable[
    ...,
    Awaitable[dict[str, Any]],
]


async def post_debug_clinical_extraction_to_worker(
    *,
    settings: Settings,
    work_item: dict[str, Any],
    provider: str | None,
    model: str | None,
) -> dict[str, Any]:
    if not settings.clinical_extraction_worker_base_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CLINICAL_EXTRACTION_WORKER_BASE_URL is required for debug extraction",
        )

    url = (
        f"{settings.clinical_extraction_worker_base_url.rstrip('/')}"
        "/api/v1/dev/clinical-extraction/extract"
    )
    params: dict[str, str] = {}
    if provider:
        params["provider"] = provider
    if model:
        params["model"] = model

    async with httpx.AsyncClient(
        timeout=build_debug_clinical_extraction_http_timeout()
    ) as client:
        response = await client.post(url, json=work_item, params=params or None)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Debug clinical extraction worker returned invalid payload",
            )
        return payload


async def run_debug_clinical_extraction(
    *,
    payload: DebugClinicalExtractionRequest,
    db_session: AsyncSession,
    settings: Settings,
    worker_caller: WorkerCaller = post_debug_clinical_extraction_to_worker,
) -> DebugClinicalExtractionResponse:
    recording_session = None
    transcript_json: dict[str, Any]
    session_id: str

    if payload.session_id:
        recording_session = await get_debug_transcript_session(
            db_session,
            session_id=payload.session_id,
        )
        if not recording_session:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")
        transcript_json = recording_session.transcript_json
        session_id = recording_session.session_id
    else:
        transcript_json = payload.transcript_json or {}
        session_id = str(transcript_json.get("session_id") or "debug")

    language = payload.language or _transcript_language(transcript_json)
    chunks = build_extraction_chunks_from_transcript(transcript_json)
    if not chunks:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "transcript_json did not produce extraction chunks",
        )

    session_context = build_debug_recording_session_context(
        recording_session=recording_session,
        context=payload.context,
    )
    work_item = {
        "session_id": session_id,
        "encounter_id": getattr(session_context, "encounter_id", 0),
        "document_id": getattr(session_context, "document_id", 0),
        "doctor_id": getattr(session_context, "doctor_id", 0),
        "language": language,
        "chunks": [chunk.model_dump() for chunk in chunks],
    }

    try:
        worker_payload = await worker_caller(
            settings=settings,
            work_item=work_item,
            provider=payload.provider,
            model=payload.model,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            exc.response.status_code,
            exc.response.text or "Debug clinical extraction worker request failed",
        ) from exc
    except httpx.ReadTimeout as exc:
        timeout_seconds = debug_clinical_extraction_timeout_seconds()
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            (
                "Debug clinical extraction worker timed out after "
                f"{timeout_seconds:.0f}s"
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Debug clinical extraction worker is unavailable",
        ) from exc

    if not worker_payload.get("success"):
        return DebugClinicalExtractionResponse(
            session_id=session_id,
            chunks=chunks,
            status="failed_extraction",
            error_code="worker_failed",
            extraction_model=worker_payload.get("extraction_model"),
            latency_ms=worker_payload.get("latency_ms"),
        )

    raw_mentions = worker_payload.get("facts")
    if not isinstance(raw_mentions, dict):
        return DebugClinicalExtractionResponse(
            session_id=session_id,
            chunks=chunks,
            status="failed_extraction",
            error_code="invalid_worker_facts",
            extraction_model=worker_payload.get("extraction_model"),
            latency_ms=worker_payload.get("latency_ms"),
        )

    processed_mentions, evidence, grounding_stats = process_debug_clinical_mentions(
        raw_mentions,
        chunks,
        latency_ms=worker_payload.get("latency_ms"),
    )

    logger.info(
        "debug_clinical_extraction session_id=%s chunks=%s mentions=%s",
        session_id,
        len(chunks),
        int(grounding_stats.get("mentions_emitted", 0)),
    )

    return DebugClinicalExtractionResponse(
        session_id=session_id,
        chunks=chunks,
        raw_mentions=raw_mentions,
        processed_mentions=processed_mentions,
        evidence=evidence,
        grounding_stats=grounding_stats,
        extraction_model=worker_payload.get("extraction_model"),
        latency_ms=worker_payload.get("latency_ms"),
        status="extracted",
    )
