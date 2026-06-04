from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app, processor
from app.vad import VadResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_debug_transcription_endpoint_returns_transcript(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_vad(_audio_bytes: bytes) -> VadResult:
        return VadResult(is_speech=True, speech_ms=1500, speech_ratio=0.6)

    async def fake_transcribe_audio(**_kwargs) -> str:
        return "Paciente refiere dolor."

    monkeypatch.setattr(processor, "_run_vad", fake_vad)
    monkeypatch.setattr("app.main.transcribe_audio", fake_transcribe_audio)

    response = client.post(
        "/api/v1/dev/transcription/debug",
        files={"file": ("sample.webm", b"audio-bytes", "audio/webm")},
        data={"provider": "openai", "model": "gpt-4o-mini-transcribe"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o-mini-transcribe"
    assert payload["transcript"] == "Paciente refiere dolor."
    assert payload["vad_decision"] == "speech"


def test_debug_transcription_endpoint_returns_no_speech_without_transcript(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_vad(_audio_bytes: bytes) -> VadResult:
        return VadResult(is_speech=False, speech_ms=0, speech_ratio=0.0)

    async def fail_transcribe_audio(**_kwargs) -> str:
        raise AssertionError("transcribe_audio should not be called for no speech")

    monkeypatch.setattr(processor, "_run_vad", fake_vad)
    monkeypatch.setattr("app.main.transcribe_audio", fail_transcribe_audio)

    response = client.post(
        "/api/v1/dev/transcription/debug",
        files={"file": ("sample.webm", b"audio-bytes", "audio/webm")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == ""
    assert payload["vad_decision"] == "no_speech"
