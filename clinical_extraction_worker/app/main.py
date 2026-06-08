from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request

from app.auth import verify_cloud_tasks_request
from app.processor import Processor
from app.settings import Settings

settings = Settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VextHealth Clinical Extraction Worker",
    version="0.1.0",
    docs_url="/api/v1/docs" if settings.is_local else None,
    openapi_url="/api/v1/openapi.json" if settings.is_local else None,
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
