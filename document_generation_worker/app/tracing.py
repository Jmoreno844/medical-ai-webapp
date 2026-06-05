from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from app.settings import Settings

logger = logging.getLogger(__name__)
_initialized = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _has_otlp_endpoint_env() -> bool:
    if (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip():
        return True
    return bool((os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip())


def _resolve_exporter_mode() -> str:
    if _env_bool("OTEL_SDK_DISABLED"):
        return "none"
    explicit = (os.environ.get("OTEL_TRACES_EXPORTER") or "").strip().lower()
    if explicit in {"none", "off", "no", "false"}:
        return "none"
    if explicit in {"otlp", "otlp_http"}:
        return "otlp"
    if explicit in {"gcp", "gcp_trace", "google_cloud_trace"}:
        return "gcp"

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if project and not _env_bool("OTEL_FORCE_OTLP"):
        return "gcp"
    if _has_otlp_endpoint_env():
        return "otlp"
    return "none"


def _otlp_traces_endpoint() -> str | None:
    direct = (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
    if direct:
        return direct
    base = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip().rstrip("/")
    if not base:
        return None
    if base.endswith("/v1/traces"):
        return base
    return f"{base}/v1/traces"


def configure_tracing(
    app: FastAPI,
    settings: Settings,
    *,
    service_name: str,
) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    mode = _resolve_exporter_mode()
    if mode == "none":
        logger.info("Tracing disabled", extra={"event": "otel_disabled"})
        return

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name}),
            sampler=ParentBased(TraceIdRatioBased(ratio)),
        )
        if mode == "otlp":
            endpoint = _otlp_traces_endpoint()
            if not endpoint:
                logger.warning(
                    "OTLP selected without endpoint",
                    extra={"event": "otel_missing_endpoint"},
                )
                return
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint)))
        else:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        logger.info(
            "Tracing initialized",
            extra={"event": "otel_initialized", "provider": mode},
        )
    except Exception:
        logger.exception(
            "Tracing init failed; continuing without tracing",
            extra={"event": "otel_init_failed"},
        )
