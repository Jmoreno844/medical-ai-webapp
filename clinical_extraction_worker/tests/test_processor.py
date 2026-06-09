from __future__ import annotations

import asyncio

import pytest

from app.processor import Processor
from app.settings import Settings


class FakeBackend:
    def __init__(self) -> None:
        self.callbacks: list[dict] = []

    async def fetch_work_item(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "encounter_id": 1,
            "document_id": 2,
            "doctor_id": 3,
            "language": None,
            "chunks": [],
            "callback_token": "token",
        }

    async def post_result(
        self,
        session_id: str,
        *,
        callback_token: str,
        payload: dict,
    ) -> None:
        self.callbacks.append(
            {
                "session_id": session_id,
                "callback_token": callback_token,
                **payload,
            }
        )


@pytest.mark.asyncio
async def test_processor_posts_extracted_result(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(_env_file=None, ENVIRONMENT="test"),
        backend=backend,
        llm_semaphore=asyncio.Semaphore(1),
    )

    async def fake_extract(**_kwargs):
        return {
            "mentions": [],
        }

    monkeypatch.setattr("app.processor.extract_clinical_facts", fake_extract)

    await processor.process_session("sess-1", {"session_id": "sess-1"})

    assert backend.callbacks[-1]["status"] == "extracted"
    assert backend.callbacks[-1]["extraction_model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_processor_posts_failed_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(_env_file=None, ENVIRONMENT="test"),
        backend=backend,
        llm_semaphore=asyncio.Semaphore(1),
    )

    async def fake_extract(**_kwargs):
        raise RuntimeError("llm_down")

    monkeypatch.setattr("app.processor.extract_clinical_facts", fake_extract)

    await processor.process_session("sess-1", {"session_id": "sess-1"})

    assert backend.callbacks[-1]["status"] == "failed_extraction"
    assert backend.callbacks[-1]["error_code"] == "RuntimeError"


@pytest.mark.asyncio
async def test_processor_rejects_mismatched_payload() -> None:
    processor = Processor(
        settings=Settings(_env_file=None, ENVIRONMENT="test"),
        backend=FakeBackend(),
        llm_semaphore=asyncio.Semaphore(1),
    )

    with pytest.raises(ValueError):
        await processor.process_session("sess-1", {"session_id": "other"})
