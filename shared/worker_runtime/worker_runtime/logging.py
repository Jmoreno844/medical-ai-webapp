from __future__ import annotations

import logging
from collections.abc import Iterable

from worker_runtime.observability import (
    JsonTelemetryFormatter,
    SensitiveTelemetryFilter,
    TraceContextFilter,
)
from worker_runtime.settings import BaseWorkerSettings


def configure_logging(
    settings: BaseWorkerSettings,
    *,
    service_name: str,
    noisy_logger_names: Iterable[str] = (),
) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

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

    for noisy_logger_name in noisy_logger_names:
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)
