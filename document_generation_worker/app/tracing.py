from __future__ import annotations

import logging

from app.settings import Settings

logger = logging.getLogger(__name__)
_initialized = False


def configure_tracing(settings: Settings) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True
    if settings.is_local:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": "vexthealth-document-generation-worker"}
            ),
            sampler=ParentBased(TraceIdRatioBased(1.0)),
        )
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(provider)
        HTTPXClientInstrumentor().instrument()
        logger.info("OpenTelemetry initialized for document generation worker")
    except Exception:
        logger.exception("OpenTelemetry init failed; continuing without tracing")
