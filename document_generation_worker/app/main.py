from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request

from app.auth import verify_cloud_tasks_request
from app.langsmith_tracing import configure_langsmith
from app.logging_config import configure_logging
from app.processor import Processor
from app.settings import Settings
from app.tracing import configure_tracing

settings = Settings()
configure_logging(settings)
configure_tracing(settings)
configure_langsmith(settings)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VextHealth Document Generation Worker",
    version="0.1.0",
    docs_url="/api/v1/docs" if settings.is_local else None,
    openapi_url="/api/v1/openapi.json" if settings.is_local else None,
)
processor = Processor.create(settings)


def get_processor() -> Processor:
    return processor


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "document-generation-worker"}


@app.post("/api/v1/internal/document-generation/tasks/{process_id}")
async def run_document_generation_task(
    process_id: str,
    payload: dict,
    request: Request,
    worker: Processor = Depends(get_processor),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    await worker.process_task(process_id, payload)
    return {"success": True}
