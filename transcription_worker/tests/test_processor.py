from __future__ import annotations

import pytest

from app.processor import Processor
from app.settings import Settings
from app.vad import VadResult


class FakeBackend:
    def __init__(self) -> None:
        self.section_results: list[dict] = []

    async def get_section_work_item(self, section_id: str) -> dict:
        return {
            "section_id": section_id,
            "session_id": "session-1",
            "gcs_object_name": "encounter_audio/1/test.webm",
            "gcs_uri": "gs://bucket/encounter_audio/1/test.webm",
            "content_type": "audio/webm",
        }

    async def post_section_result(self, section_id: str, payload: dict) -> None:
        self.section_results.append({"section_id": section_id, **payload})


@pytest.mark.asyncio
async def test_no_speech_section_skips_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(ENVIRONMENT="test"),
        backend=backend,
        vad_semaphore=None,  # type: ignore[arg-type]
        gemini_semaphore=None,  # type: ignore[arg-type]
    )

    async def fake_download_audio(_object_name: str) -> bytes:
        return b"audio"

    async def fake_vad(_audio_bytes: bytes) -> VadResult:
        return VadResult(is_speech=False, speech_ms=0, speech_ratio=0.0)

    async def fail_gemini(**_kwargs) -> str:
        raise AssertionError("Gemini should not be called for no-speech sections")

    monkeypatch.setattr(processor, "_download_audio_bytes", fake_download_audio)
    monkeypatch.setattr(processor, "_run_vad", fake_vad)
    monkeypatch.setattr("app.processor.transcribe_audio", fail_gemini)

    await processor.process_section("section-1")

    assert backend.section_results[0]["status"] == "discarded_no_speech"


@pytest.mark.asyncio
async def test_vad_error_fails_open_to_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(ENVIRONMENT="test"),
        backend=backend,
        vad_semaphore=None,  # type: ignore[arg-type]
        gemini_semaphore=__import__("asyncio").Semaphore(1),
    )

    async def fake_download_audio(_object_name: str) -> bytes:
        return b"audio"

    async def fake_vad(_audio_bytes: bytes) -> VadResult:
        return VadResult(
            is_speech=True,
            speech_ms=0,
            speech_ratio=0.0,
            error_code="vad_error",
        )

    async def fake_gemini(**_kwargs) -> str:
        return "Paciente refiere dolor."

    monkeypatch.setattr(processor, "_download_audio_bytes", fake_download_audio)
    monkeypatch.setattr(processor, "_run_vad", fake_vad)
    monkeypatch.setattr("app.processor.transcribe_audio", fake_gemini)

    await processor.process_section("section-1")

    assert backend.section_results[0]["status"] == "transcribed"
    assert backend.section_results[0]["vad_decision"] == "fail_open"


@pytest.mark.asyncio
async def test_openai_provider_receives_audio_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = Processor(
        settings=Settings(
            ENVIRONMENT="test",
            TRANSCRIPTION_PROVIDER="openai",
            TRANSCRIPTION_MODEL="gpt-4o-mini-transcribe",
        ),
        backend=backend,
        vad_semaphore=None,  # type: ignore[arg-type]
        gemini_semaphore=__import__("asyncio").Semaphore(1),
    )

    async def fake_download_audio(_object_name: str) -> bytes:
        return b"audio-bytes"

    async def fake_vad(_audio_bytes: bytes) -> VadResult:
        return VadResult(is_speech=True, speech_ms=1200, speech_ratio=0.7)

    captured: dict[str, object] = {}

    async def fake_transcribe(**kwargs) -> str:
        captured.update(kwargs)
        return "Paciente refiere dolor."

    monkeypatch.setattr(processor, "_download_audio_bytes", fake_download_audio)
    monkeypatch.setattr(processor, "_run_vad", fake_vad)
    monkeypatch.setattr("app.processor.transcribe_audio", fake_transcribe)

    await processor.process_section("section-1")

    assert backend.section_results[0]["status"] == "transcribed"
    assert captured["audio_bytes"] == b"audio-bytes"
    assert captured["gcs_uri"] == "gs://bucket/encounter_audio/1/test.webm"
