from __future__ import annotations

import logging

from app.core.observability import (
    JsonTelemetryFormatter,
    SensitiveTelemetryFilter,
    TraceContextFilter,
)
from app.core.settings.base import Settings


def configure_logging(settings: Settings, *, service_name: str) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.debug and "DEBUG" or "INFO"))

    handler = logging.StreamHandler()
    handler.setFormatter(JsonTelemetryFormatter())
    handler.addFilter(SensitiveTelemetryFilter())
    handler.addFilter(
        TraceContextFilter(
            service_name=service_name,
            environment=settings.environment,
        )
    )
    root.addHandler(handler)
