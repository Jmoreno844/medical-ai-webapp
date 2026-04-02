"""
Shared Django LOGGING dict builder. Level is controlled by env ``DJANGO_LOG_LEVEL``
(``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``). Invalid values fall back to *default_level*.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

_VALID = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

_RESET = "\x1b[0m"
_LEVEL_COLORS = {
    "DEBUG": "\x1b[36m",
    "INFO": "\x1b[32m",
    "WARNING": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "CRITICAL": "\x1b[35;1m",
}

_HTTP_STATUS_COLORS = (
    ((100, 199), "\x1b[36m"),
    ((200, 299), "\x1b[32m"),
    ((300, 399), "\x1b[36m"),
    ((400, 499), "\x1b[33m"),
    ((500, 599), "\x1b[31m"),
)


class TraceContextFilter(logging.Filter):
    """Attach trace/span IDs from the current OpenTelemetry span to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace
            from opentelemetry.trace import format_span_id, format_trace_id

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


def color_enabled() -> bool:
    force_color = os.getenv("FORCE_COLOR", "").strip().lower()
    if force_color in {"1", "true", "yes", "on"}:
        return True

    no_color = os.getenv("NO_COLOR", "").strip().lower()
    if no_color in {"1", "true", "yes", "on"}:
        return False

    term = os.getenv("TERM", "").strip().lower()
    return bool(term and term != "dumb")


class ColorConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        if color_enabled():
            color = _LEVEL_COLORS.get(record.levelname)
            if color:
                record.levelname = f"{color}{record.levelname}{_RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


class ForceColorServerFormatter(logging.Formatter):
    default_time_format = "%d/%b/%Y %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.msg
        if color_enabled():
            status_code = getattr(record, "status_code", None)
            if isinstance(status_code, int):
                for (start, end), color in _HTTP_STATUS_COLORS:
                    if start <= status_code <= end:
                        record.msg = f"{color}{record.msg}{_RESET}"
                        break

        if self.usesTime() and not hasattr(record, "server_time"):
            record.server_time = self.formatTime(record, self.datefmt)

        try:
            return super().format(record)
        finally:
            record.msg = original_msg


def resolve_log_level(default_level: str) -> str:
    raw = os.getenv("DJANGO_LOG_LEVEL", default_level).strip().upper()
    return raw if raw in _VALID else default_level.upper()


def build_console_logging(default_level: str = "INFO") -> Dict[str, Any]:
    level = resolve_log_level(default_level)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "trace_context": {
                "()": "config.settings.logging_utils.TraceContextFilter",
            },
        },
        "formatters": {
            "standard": {
                "()": "config.settings.logging_utils.ColorConsoleFormatter",
                "format": (
                    "[{levelname}] {asctime} {name} trace_id={trace_id} "
                    "span_id={span_id} {message}"
                ),
                "style": "{",
            },
            "django.server": {
                "()": "config.settings.logging_utils.ForceColorServerFormatter",
                "format": "[{server_time}] {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "filters": ["trace_context"],
            },
            "django.server": {
                "class": "logging.StreamHandler",
                "formatter": "django.server",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.server": {
                "handlers": ["django.server"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
