from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.observability import log_event
from app.core.tracing import configure_tracing
from app.core.middleware import SecurityHeadersMiddleware
from app.domains.copilot.internal_tools_api import router as copilot_internal_tools_router

settings = get_settings()
configure_logging(settings, service_name="vexthealth-backend")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Medical API FastAPI Migration",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)
app.state.settings = settings
configure_tracing(app, settings, service_name="vexthealth-backend")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"],
    allow_headers=[
        "accept",
        "authorization",
        "content-type",
        "origin",
        "traceparent",
        "tracestate",
        "x-csrftoken",
        "x-requested-with",
    ],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
app.include_router(copilot_internal_tools_router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_event(
        logger,
        logging.ERROR,
        "Unhandled API exception",
        event="unhandled_api_exception",
        error_code=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_code": type(exc).__name__,
        },
    )
