from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status

from app.auth import require_internal_bearer_token
from app.config import get_settings
from app.langsmith import configure_langsmith
from app.logging_config import configure_logging
from app.runtime import CopilotRuntime
from app.schemas import RunCreateRequest, RunResumeRequest

settings = get_settings()
configure_logging(settings.log_level)
configure_langsmith(settings)
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
async def create_run(
    request: RunCreateRequest,
    background_tasks: BackgroundTasks,
    _token_payload: dict[str, object] = Depends(require_internal_bearer_token),
) -> dict[str, object]:
    run_id = str(uuid.uuid4())
    # Create the run record and emit run_started immediately so FastAPI can return
    # run_id to the browser within ~50 ms instead of blocking for 15-30 s.
    # The graph runs as a BackgroundTask: uvicorn's event loop keeps the background
    # coroutine alive until it completes even after the HTTP response is sent.
    # FastAPI's existing SSE polling (stream_copilot_run) delivers events to the
    # browser as they land in DB — typically within 1 s of each graph step.
    stored_run, events = await asyncio.to_thread(
        runtime.bootstrap_run, request, run_id=run_id
    )
    background_tasks.add_task(runtime.run_graph_async, run_id=run_id, request=request)
    logger.info(
        "Bootstrapped copilot run (graph running in background)",
        extra={
            "run_id": run_id,
            "thread_id": request.thread_id,
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
