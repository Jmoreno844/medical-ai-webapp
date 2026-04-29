from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from app.auth import verify_cloud_tasks_request
from app.logging_config import configure_logging
from app.processor import Processor
from app.settings import Settings

settings = Settings()
configure_logging(settings)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VextHealth Transcription Worker",
    version="0.1.0",
    docs_url="/api/v1/docs" if settings.is_local else None,
    openapi_url="/api/v1/openapi.json" if settings.is_local else None,
)
processor = Processor.create(settings)


class EmptyPayload(BaseModel):
    pass


def get_processor() -> Processor:
    return processor


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "transcription-worker"}


@app.post("/api/v1/internal/transcription/tasks/sections/{section_id}")
async def run_section_task(
    section_id: str,
    request: Request,
    _payload: EmptyPayload | None = None,
    worker: Processor = Depends(get_processor),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    await worker.process_section(section_id)
    return {"success": True}
