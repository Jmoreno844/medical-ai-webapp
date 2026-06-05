from __future__ import annotations

import asyncio

import pytest

from app.processor import Processor
from app.settings import Settings


class FakeBackend:
    def __init__(self) -> None:
        self.callbacks: list[dict] = []

    async def fetch_work_item(self, process_id: str, payload: dict) -> dict:
        return {
            "process_id": process_id,
            "doctor_id": payload["doctor_id"],
            "new_document_id": payload["new_document_id"],
            "context_document_id": payload["context_document_id"],
            "transcription_document_id": payload["transcription_document_id"],
            "doctor_template_id": payload["doctor_template_id"],
            "encounter_id": 99,
            "context_content": "No se agregó contexto.",
            "transcription_content": "Paciente refiere dolor.",
            "template_content": "## Motivo",
            "callback_token": "token",
        }

    async def post_generation_chunk(
        self,
        *,
        callback_token: str,
        payload: dict,
    ) -> None:
        self.callbacks.append({"callback_token": callback_token, **payload})


TASK_PAYLOAD = {
    "process_id": "gen_1",
    "doctor_id": 7,
    "new_document_id": 11,
    "context_document_id": 12,
    "transcription_document_id": 13,
    "doctor_template_id": 14,
}


@pytest.mark.asyncio
async def test_processor_streams_chunks_and_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(ENVIRONMENT="test", DOCUMENT_GENERATION_CHUNK_SIZE=5),
        backend=backend,
        llm_semaphore=asyncio.Semaphore(1),
    )

    async def fake_stream(**_kwargs):
        yield "Hola "
        yield "mundo"

    monkeypatch.setattr("app.processor.stream_document_generation", fake_stream)

    await processor.process_task("gen_1", TASK_PAYLOAD)

    assert backend.callbacks[-1]["is_complete"] is True
    assert backend.callbacks[-1]["chunk"] == "Hola mundo"


@pytest.mark.asyncio
async def test_processor_raises_before_first_chunk_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(ENVIRONMENT="test"),
        backend=backend,
        llm_semaphore=asyncio.Semaphore(1),
    )

    async def failing_stream(**_kwargs):
        raise RuntimeError("llm_down")
        yield ""

    monkeypatch.setattr("app.processor.stream_document_generation", failing_stream)

    with pytest.raises(RuntimeError):
        await processor.process_task("gen_1", TASK_PAYLOAD)

    assert backend.callbacks == []
