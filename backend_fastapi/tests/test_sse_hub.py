import pytest

from app.domains.documents.sse_hub import (
    publish_document_event,
    subscribe,
    unsubscribe,
)


@pytest.mark.asyncio
async def test_sse_hub_delivers_event_to_document_subscriber() -> None:
    queue = await subscribe(99)

    try:
        await publish_document_event(99, "generation_chunk", {"chunk": "hola"})
        message = await queue.get()
    finally:
        await unsubscribe(99, queue)

    assert "generation_chunk" in message
    assert "hola" in message

