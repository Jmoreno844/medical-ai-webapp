"""
OpenTelemetry bootstrap for Django. Call ``configure_tracing()`` from WSGI/ASGI
before ``get_wsgi_application`` / ``get_asgi_application``.

Exporter selection (first match wins unless ``OTEL_TRACES_EXPORTER`` is set):

- ``OTEL_SDK_DISABLED`` / ``OTEL_TRACES_EXPORTER=none`` — no export
- ``OTEL_TRACES_EXPORTER=otlp`` — OTLP/HTTP (Jaeger, etc.)
- ``OTEL_TRACES_EXPORTER=gcp`` — Google Cloud Trace
- If ``GOOGLE_CLOUD_PROJECT`` or ``GCP_PROJECT`` is set — Cloud Trace
- Else if ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` or ``OTEL_EXPORTER_OTLP_ENDPOINT``
  is set — OTLP/HTTP
- Otherwise tracing is disabled
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_initialized = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _has_otlp_endpoint_env() -> bool:
    if (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip():
        return True
    return bool((os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip())


def _resolve_exporter_mode() -> str:
    if _env_bool("OTEL_SDK_DISABLED"):
        return "none"
    explicit = (os.environ.get("OTEL_TRACES_EXPORTER") or "").strip().lower()
    if explicit:
        if explicit in ("none", "off", "no", "false"):
            return "none"
        if explicit in ("otlp", "otlp_http"):
            return "otlp"
        if explicit in ("gcp", "gcp_trace", "google_cloud_trace"):
            return "gcp"

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if project and not _env_bool("OTEL_FORCE_OTLP"):
        return "gcp"
    if _has_otlp_endpoint_env():
        return "otlp"
    return "none"


def _otlp_traces_endpoint() -> Optional[str]:
    direct = (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
    if direct:
        return direct
    base = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip().rstrip("/")
    if not base:
        return None
    if base.endswith("/v1/traces"):
        return base
    return f"{base}/v1/traces"


def configure_tracing() -> None:
    """Idempotent SDK + Django + requests instrumentation."""
    global _initialized
    if _initialized:
        return

    mode = _resolve_exporter_mode()
    if mode == "none":
        logger.debug("OpenTelemetry: tracing disabled (no exporter configured)")
        _initialized = True
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", "vexthealth-backend")

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        sampler = ParentBased(TraceIdRatioBased(ratio))
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource, sampler=sampler)
        trace.set_tracer_provider(provider)

        if mode == "otlp":
            endpoint = _otlp_traces_endpoint()
            if not endpoint:
                logger.warning(
                    "OpenTelemetry: OTLP mode but no OTLP endpoint; tracing disabled"
                )
                _initialized = True
                return
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        elif mode == "gcp":
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))

        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        DjangoInstrumentor().instrument()
        RequestsInstrumentor().instrument()

        logger.info(
            "OpenTelemetry: initialized service=%s exporter=%s",
            service_name,
            mode,
        )
    except Exception:
        logger.exception(
            "OpenTelemetry: failed to initialize; continuing without tracing"
        )
    finally:
        _initialized = True
