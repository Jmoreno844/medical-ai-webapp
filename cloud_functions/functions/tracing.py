"""
OpenTelemetry for Cloud Functions (Python). See backend ``config/tracing.py`` for
env var semantics (OTLP vs GCP vs disabled).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, TypeVar

logger = logging.getLogger(__name__)

_initialized = False
_exporting = False

T = TypeVar("T")


def _env_bool(name: str, default: bool = False) -> bool:
    import os

    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _has_otlp_endpoint_env() -> bool:
    import os

    if (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip():
        return True
    return bool((os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip())


def _resolve_exporter_mode() -> str:
    import os

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
    import os

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
    global _initialized, _exporting
    if _initialized:
        return

    import os

    mode = _resolve_exporter_mode()
    if mode == "none":
        logger.debug("OpenTelemetry: tracing disabled for Cloud Functions")
        _initialized = True
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", "vexthealth-cloud-functions")

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
                    "OpenTelemetry: OTLP selected but no endpoint; tracing disabled"
                )
                _initialized = True
                return
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint)))
        elif mode == "gcp":
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(CloudTraceSpanExporter())
            )

        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()

        _exporting = True
        attach_trace_logging_filter()
        logger.info(
            "OpenTelemetry: Cloud Functions initialized service=%s exporter=%s",
            service_name,
            mode,
        )
    except Exception:
        logger.exception(
            "OpenTelemetry: Cloud Functions init failed; continuing without tracing"
        )
    finally:
        _initialized = True


@contextmanager
def server_span(request: Any, name: str) -> Iterator[Any]:
    configure_tracing()
    if not _exporting:
        yield None
        return

    from opentelemetry import trace
    from opentelemetry.propagate import extract
    from opentelemetry.trace import SpanKind, Status, StatusCode

    carrier = {k: v for k, v in request.headers.items()}
    ctx = extract(carrier)
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(
        name, context=ctx, kind=SpanKind.SERVER
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def run_with_request_span(
    request: Any,
    span_name: str,
    handler: Callable[[Any], T],
) -> T:
    with server_span(request, span_name):
        return handler(request)


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace
            from opentelemetry.trace import format_span_id, format_trace_id

            import os

            span = trace.get_current_span()
            sc = span.get_span_context()
            if sc.is_valid:
                record.trace_id = format_trace_id(sc.trace_id)
                record.span_id = format_span_id(sc.span_id)
                project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
                if project:
                    record.google_cloud_trace = (
                        f"projects/{project}/traces/{format_trace_id(sc.trace_id)}"
                    )
                else:
                    record.google_cloud_trace = "-"
            else:
                record.trace_id = "-"
                record.span_id = "-"
                record.google_cloud_trace = "-"
        except Exception:
            record.trace_id = "-"
            record.span_id = "-"
            record.google_cloud_trace = "-"
        return True


def attach_trace_logging_filter() -> None:
    root = logging.getLogger()
    if not any(type(f) is TraceContextFilter for f in root.filters):
        root.addFilter(TraceContextFilter())
