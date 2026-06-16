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
            "context_inputs": {
                "doctor_note_markdown": "No se agregó contexto.",
                "external_documents": [],
            },
            "context_content": "No se agregó contexto.",
            "template": {
                "id": "doctor_template_14",
                "name": "SOAP",
                "document_kind": "clinical",
                "sections": [
                    {"section_id": "motivo", "heading": "Motivo", "description": ""},
                ],
            },
            "transcription_turns": [
                {"turn_id": 0, "speaker": "PACIENTE", "text": "Dolor de cabeza."},
            ],
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
async def test_processor_completes_pipeline_with_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(ENVIRONMENT="test"),
        backend=backend,
        llm_semaphore=asyncio.Semaphore(1),
    )

    from app.pipeline import orchestrator

    def fake_run_document_pipeline(**_kwargs):
        if _kwargs.get("on_step_complete"):
            _kwargs["on_step_complete"]("filtering", {"duration_ms": 1})
        if _kwargs.get("on_section_complete"):
            _kwargs["on_section_complete"]("motivo", "Motivo", "## Motivo\n\nContenido.")
        from app.pipeline.orchestrator import PipelineRunResult, PipelineStepResult

        return PipelineRunResult(
            document_markdown="## Motivo\n\nContenido.",
            step_results=[PipelineStepResult("filtering", 1, {})],
        )

    monkeypatch.setattr("app.processor.run_document_pipeline", fake_run_document_pipeline)

    await processor.process_task("gen_1", TASK_PAYLOAD)

    assert backend.callbacks[-1]["is_complete"] is True
    assert "Motivo" in backend.callbacks[-1]["chunk"]


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

    from app.pipeline import orchestrator

    def failing_pipeline(**_kwargs):
        raise RuntimeError("llm_down")

    monkeypatch.setattr("app.processor.run_document_pipeline", failing_pipeline)

    with pytest.raises(RuntimeError):
        await processor.process_task("gen_1", TASK_PAYLOAD)

    assert backend.callbacks == []
