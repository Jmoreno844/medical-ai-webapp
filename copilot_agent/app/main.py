from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status

from app.auth import require_internal_bearer_token
from app.config import get_settings
from app.logging_config import configure_logging
from app.runtime import CopilotRuntime
from app.schemas import RunCreateRequest, RunResumeRequest

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
runtime = CopilotRuntime(settings=settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime.setup()
    yield

app = FastAPI(
    title="Copilot Agent Service",
    version="0.1.0",
    description="Dedicated LangGraph runtime for the clinical copilot.",
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "copilot-agent-service"}


@app.post("/internal/copilot/runs")
def create_run(
    request: RunCreateRequest,
    _token_payload: dict[str, object] = Depends(require_internal_bearer_token),
) -> dict[str, object]:
    stored_run, events = runtime.create_run(request)
    logger.info(
        "Created copilot run",
        extra={
            "run_id": stored_run.run_id,
            "thread_id": stored_run.thread_id,
            "trace_id": request.trace_metadata.get("trace_id"),
        },
    )
    return {
        "run": runtime.to_status_response(stored_run).model_dump(mode="python"),
        "events": [event.model_dump(mode="python") for event in events],
    }


@app.post("/internal/copilot/runs/{run_id}/resume")
def resume_run(
    run_id: str,
    request: RunResumeRequest,
    _token_payload: dict[str, object] = Depends(require_internal_bearer_token),
) -> dict[str, object]:
    try:
        stored_run, events = runtime.resume_run(run_id, request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Run not found") from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return {
        "run": runtime.to_status_response(stored_run).model_dump(mode="python"),
        "events": [event.model_dump(mode="python") for event in events],
    }


@app.get("/internal/copilot/runs/{run_id}")
def get_run(
    run_id: str,
    _token_payload: dict[str, object] = Depends(require_internal_bearer_token),
) -> dict[str, object]:
    try:
        stored_run = runtime.get_run(run_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Run not found") from error

    return runtime.to_status_response(stored_run).model_dump(mode="python")


@app.get("/internal/copilot/runs/{run_id}/events")
def get_run_events(
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    _token_payload: dict[str, object] = Depends(require_internal_bearer_token),
) -> dict[str, object]:
    try:
        events = runtime.list_run_events(run_id, after_sequence=after_sequence)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Run not found") from error

    return events.model_dump(mode="python")
