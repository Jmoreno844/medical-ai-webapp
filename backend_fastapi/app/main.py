from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import SecurityHeadersMiddleware


configure_logging()
settings = get_settings()

app = FastAPI(
    title="Medical API FastAPI Migration",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

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

