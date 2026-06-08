from __future__ import annotations

import asyncio

import pytest

from app.processor import Processor
from app.settings import Settings
from app.vad import VadResult
from transcription_contract.models import TranscriptionTurn


class FakeBackend:
    def __init__(self) -> None:
        self.section_results: list[dict] = []

    async def get_section_work_item(self, section_id: str) -> dict:
        return {
            "section_id": section_id,
            "session_id": "session-1",
            "clipped_gcs_object_name": "encounter_audio/1/clipped.ogg",
            "clipped_gcs_uri": "gs://bucket/encounter_audio/1/clipped.ogg",
            "clipped_content_type": "audio/ogg",
            "transcription_source_gcs_object_name": "encounter_audio/1/clipped.ogg",
            "transcription_source_gcs_uri": "gs://bucket/encounter_audio/1/clipped.ogg",
            "transcription_source_content_type": "audio/ogg",
            "original_gcs_object_name": "encounter_audio/1/original.webm",
        }

    async def post_section_result(self, section_id: str, payload: dict) -> None:
        self.section_results.append({"section_id": section_id, **payload})


def build_processor(backend: FakeBackend) -> Processor:
    return Processor(
        settings=Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai"),
        backend=backend,
        vad_semaphore=asyncio.Semaphore(1),
        gemini_semaphore=asyncio.Semaphore(1),
    )


def _sample_turns(text: str = "Paciente refiere dolor.") -> list[TranscriptionTurn]:
    return [TranscriptionTurn(speaker="PACIENTE", text=text)]


@pytest.mark.asyncio
async def test_happy_path_transcribes_from_gcs_without_downloading_clipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = build_processor(backend)
    downloaded_objects: list[str] = []
    captured_calls: list[dict[str, object]] = []

    async def fake_download_audio(object_name: str) -> bytes:
        downloaded_objects.append(object_name)
        return b"original-audio"

    async def fake_transcribe(**kwargs) -> list[TranscriptionTurn]:
        captured_calls.append(kwargs)
        return _sample_turns()

    monkeypatch.setattr(processor, "_download_audio_bytes", fake_download_audio)
    monkeypatch.setattr("app.processor.transcribe_chunk_audio", fake_transcribe)

    await processor.process_section("section-1")

    assert downloaded_objects == []
    assert len(captured_calls) == 1
    assert captured_calls[0]["gcs_uri"] == "gs://bucket/encounter_audio/1/clipped.ogg"
    assert captured_calls[0]["audio_bytes"] is None
    assert backend.section_results[0]["status"] == "transcribed"
    assert backend.section_results[0]["transcription_source"] == "clipped_frontend"
    assert backend.section_results[0]["turns"][0]["speaker"] == "PACIENTE"


@pytest.mark.asyncio
async def test_empty_clipped_transcript_downloads_only_original_for_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = build_processor(backend)
    downloaded_objects: list[str] = []
    transcribe_calls: list[dict[str, object]] = []

    async def fake_download_audio(object_name: str) -> bytes:
        downloaded_objects.append(object_name)
        return b"original-audio"

    async def fake_transcribe(**kwargs) -> list[TranscriptionTurn]:
        transcribe_calls.append(kwargs)
        if len(transcribe_calls) == 1:
            return []
        return _sample_turns()

    async def fake_build_worker_fallback_audio(
        _audio_bytes: bytes,
    ) -> tuple[VadResult, bytes]:
        return (
            VadResult(is_speech=True, speech_ms=1200, speech_ratio=0.7),
            b"trimmed-fallback-audio",
        )

    monkeypatch.setattr(processor, "_download_audio_bytes", fake_download_audio)
    monkeypatch.setattr(
        processor,
        "_build_worker_fallback_audio",
        fake_build_worker_fallback_audio,
    )
    monkeypatch.setattr("app.processor.transcribe_chunk_audio", fake_transcribe)

    await processor.process_section("section-1")

    assert downloaded_objects == ["encounter_audio/1/original.webm"]
    assert len(transcribe_calls) == 2
    assert transcribe_calls[0]["gcs_uri"] == "gs://bucket/encounter_audio/1/clipped.ogg"
    assert transcribe_calls[0]["audio_bytes"] is None
    assert transcribe_calls[1]["gcs_uri"] is None
    assert transcribe_calls[1]["audio_bytes"] == b"trimmed-fallback-audio"
    assert backend.section_results[0]["status"] == "transcribed"
    assert backend.section_results[0]["transcription_source"] == "fallback_worker_from_original"


@pytest.mark.asyncio
async def test_no_speech_fallback_discards_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    processor = build_processor(backend)
    downloaded_objects: list[str] = []

    async def fake_download_audio(object_name: str) -> bytes:
        downloaded_objects.append(object_name)
        return b"original-audio"

    async def fake_transcribe(**_kwargs) -> list[TranscriptionTurn]:
        return []

    async def fake_build_worker_fallback_audio(
        _audio_bytes: bytes,
    ) -> tuple[VadResult, bytes]:
        return (
            VadResult(is_speech=False, speech_ms=0, speech_ratio=0.0, error_code=None),
            b"trimmed-fallback-audio",
        )

    monkeypatch.setattr(processor, "_download_audio_bytes", fake_download_audio)
    monkeypatch.setattr(
        processor,
        "_build_worker_fallback_audio",
        fake_build_worker_fallback_audio,
    )
    monkeypatch.setattr("app.processor.transcribe_chunk_audio", fake_transcribe)

    await processor.process_section("section-1")

    assert downloaded_objects == ["encounter_audio/1/original.webm"]
    assert backend.section_results[0]["status"] == "discarded_no_speech"
    assert backend.section_results[0]["turns"] == []
    assert backend.section_results[0]["transcription_source"] == "fallback_worker_from_original"
