from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

_channels: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)
_lock = asyncio.Lock()


def get_processing_id(document_id: int) -> str:
    return f"gen_{document_id}_{int(datetime.now(timezone.utc).timestamp())}"


# Queues live in process memory; Cloud Run must stay on one backend instance
# until a shared broker such as Redis/Pub/Sub is introduced.
async def subscribe(document_id: int) -> asyncio.Queue[str]:
    queue: asyncio.Queue[str] = asyncio.Queue()
    async with _lock:
        _channels[str(document_id)].add(queue)
    return queue


async def unsubscribe(document_id: int, queue: asyncio.Queue[str]) -> None:
    async with _lock:
        doc_id = str(document_id)
        _channels[doc_id].discard(queue)
        if not _channels[doc_id]:
            _channels.pop(doc_id, None)


async def publish_document_event(
    document_id: int,
    event: str,
    payload: dict[str, Any] | None = None,
) -> None:
    event_payload = {
        "event": event,
        "document_id": document_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if payload:
        event_payload.update(payload)

    message = json.dumps(event_payload)
    async with _lock:
        queues = list(_channels.get(str(document_id), set()))

    for queue in queues:
        await queue.put(message)
