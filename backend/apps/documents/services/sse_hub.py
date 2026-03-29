"""
In-process SSE subscriber registry and notification helpers.

Note: queues live in process memory; multiple workers need a shared backend
to deliver events to all clients (see project documentation).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

connections_lock = threading.Lock()
event_queues: dict[str, list] = {}


def get_processing_id(document_id: int) -> str:
    """Generate a processing id for document generation jobs."""
    return f"gen_{document_id}_{int(datetime.now().timestamp())}"


def notify_document_updated(
    document_id: int, event_type: str, content: Optional[str] = None
) -> None:
    """Push an event to all SSE subscribers for this document."""
    doc_id_str = str(document_id)

    with connections_lock:
        if doc_id_str not in event_queues:
            return
        event_data = {
            "event": event_type,
            "document_id": document_id,
            "timestamp": datetime.now().isoformat(),
        }
        if content:
            event_data["content"] = content

        for queue in event_queues[doc_id_str]:
            queue.put(json.dumps(event_data))

        logger.info(
            "Sent %s event to %s clients for document %s",
            event_type,
            len(event_queues[doc_id_str]),
            document_id,
        )


def notify_generation_progress(
    document_id: int,
    process_id: str,
    chunk: Optional[str] = None,
    is_complete: bool = False,
    error: Optional[str] = None,
) -> None:
    """Push generation progress to SSE subscribers for this document."""
    doc_id_str = str(document_id)

    with connections_lock:
        if doc_id_str not in event_queues:
            return
        event_type = "generation_complete" if is_complete else "generation_chunk"
        if error:
            event_type = "generation_error"

        event_data = {
            "event": event_type,
            "document_id": document_id,
            "process_id": process_id,
            "timestamp": datetime.now().isoformat(),
        }
        if chunk:
            event_data["chunk"] = chunk
        if error:
            event_data["error"] = error

        for queue in event_queues[doc_id_str]:
            queue.put(json.dumps(event_data))

        logger.info(
            "Sent %s event for job %s to %s clients",
            event_type,
            process_id,
            len(event_queues[doc_id_str]),
        )
