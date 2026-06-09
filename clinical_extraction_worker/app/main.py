from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth import verify_cloud_tasks_request
from app.settings import Settings
from app.processor import Processor
from app.providers import extract_clinical_facts
from worker_runtime.logging import configure_logging
from worker_runtime.tracing import configure_tracing

settings = Settings()
configure_logging(
    settings,
    service_name="vexthealth-clinical-extraction-worker",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VextHealth Clinical Extraction Worker",
    version="0.1.0",
    docs_url="/api/v1/docs" if settings.is_local else None,
    openapi_url="/api/v1/openapi.json" if settings.is_local else None,
)
configure_tracing(
    app,
    settings,
    service_name="vexthealth-clinical-extraction-worker",
)
processor = Processor.create(settings)


def get_processor() -> Processor:
    return processor


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "clinical-extraction-worker"}


@app.post("/api/v1/internal/clinical-extraction/tasks/{session_id}")
async def run_clinical_extraction_task(
    session_id: str,
    payload: dict,
    request: Request,
    worker: Processor = Depends(get_processor),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    await worker.process_session(session_id, payload)
    return {"success": True}


class DebugClinicalExtractionRequest(BaseModel):
    session_id: str = "debug"
    encounter_id: int = 0
    document_id: int = 0
    doctor_id: int = 0
    language: str | None = None
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class DebugClinicalExtractionWorkerResponse(BaseModel):
    success: bool
    facts: dict[str, Any] | None
    extraction_model: str
    latency_ms: int
    provider: str


def _effective_debug_settings(
    *,
    provider: str | None,
    model: str | None,
) -> Settings:
    effective = settings.model_copy(
        update={
            "clinical_extraction_provider": provider
            or settings.clinical_extraction_provider,
        }
    )
    if not model:
        return effective
    if effective.provider_name == "openai":
        return effective.model_copy(update={"clinical_extraction_openai_model": model})
    if effective.provider_name == "anthropic_api":
        return effective.model_copy(
            update={"clinical_extraction_anthropic_model": model}
        )
    return effective.model_copy(update={"clinical_extraction_model": model})


@app.post(
    "/api/v1/dev/clinical-extraction/extract",
    response_model=DebugClinicalExtractionWorkerResponse,
)
async def debug_clinical_extraction(
    payload: DebugClinicalExtractionRequest,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    worker: Processor = Depends(get_processor),
) -> DebugClinicalExtractionWorkerResponse:
    if not settings.is_local:
        raise HTTPException(status_code=404, detail="Not found")

    effective_settings = _effective_debug_settings(provider=provider, model=model)
    started_at = time.monotonic()
    try:
        async with worker.llm_semaphore:
            facts = await extract_clinical_facts(
                work_item=payload.model_dump(),
                settings=effective_settings,
            )
    except ValueError as exc:
        logger.warning(
            "Debug clinical extraction failed",
            extra={
                "event": "debug_clinical_extraction_failed",
                "provider": effective_settings.provider_name,
                "model": effective_settings.effective_model,
                "error_code": exc.args[0] if exc.args else exc.__class__.__name__,
            },
        )
        return DebugClinicalExtractionWorkerResponse(
            success=False,
            facts=None,
            extraction_model=effective_settings.effective_model,
            latency_ms=int(round((time.monotonic() - started_at) * 1000)),
            provider=effective_settings.provider_name,
        )
    return DebugClinicalExtractionWorkerResponse(
        success=True,
        facts=facts,
        extraction_model=effective_settings.effective_model,
        latency_ms=int(round((time.monotonic() - started_at) * 1000)),
        provider=effective_settings.provider_name,
    )
