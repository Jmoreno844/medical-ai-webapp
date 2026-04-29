from __future__ import annotations

import logging

from app.settings import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "trace_id=%(otelTraceID)s span_id=%(otelSpanID)s %(message)s"
        ),
    )

    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "otelTraceID"):
            record.otelTraceID = "-"
        if not hasattr(record, "otelSpanID"):
            record.otelSpanID = "-"
        return record

    logging.setLogRecordFactory(record_factory)
