from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.vad import VadAnalysis, VadInterval


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_debug_transcription_endpoint_returns_transcript(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_transcribe_audio(**_kwargs) -> str:
        return "Paciente refiere dolor."

    def fake_build_worker_debug_cut(*_args, **_kwargs):
        return (
            VadAnalysis(
                is_speech=True,
                speech_ms=1500,
                speech_ratio=0.6,
                speech_intervals=[VadInterval(start_ms=100, end_ms=1600)],
            ),
            type(
                "WorkerCut",
                (),
                {
                    "original_duration_ms": 4000,
                    "retained_duration_ms": 2800,
                    "speech_duration_ms": 1500,
                    "speech_ratio": 0.6,
                    "retained_intervals": [VadInterval(start_ms=0, end_ms=2800)],
                    "removable_silences": [VadInterval(start_ms=2800, end_ms=4000)],
                    "speech_intervals": [VadInterval(start_ms=100, end_ms=1600)],
                    "trim_applied": True,
                },
            )(),
            b"trimmed-audio",
        )

    monkeypatch.setattr("app.main.decode_audio_to_float32_pcm", lambda _audio: b"pcm")
    monkeypatch.setattr("app.main.build_worker_debug_cut", fake_build_worker_debug_cut)
    monkeypatch.setattr("app.main.transcribe_audio", fake_transcribe_audio)

    response = client.post(
        "/api/v1/dev/transcription/debug",
        files={"file": ("sample.webm", b"audio-bytes", "audio/webm")},
        data={"provider": "legacy_provider", "model": "gemini-2.5-flash"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["mode"] == "transcribe"
    assert payload["provider"] == "google_genai"
    assert payload["model"] == "gemini-2.5-flash"
    assert payload["transcript"] == "Paciente refiere dolor."
    assert payload["vad_decision"] == "speech"
    assert payload["worker_input"]["input_byte_size"] == len(b"audio-bytes")
    assert payload["worker_input"]["decoded_duration_ms"] == 0
    assert payload["worker_cut"]["trim_applied"] is True
    assert payload["comparison"]["worker_removed_silence_ms"] == 1200


def test_debug_transcription_endpoint_returns_no_speech_without_transcript(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_transcribe_audio(**_kwargs) -> str:
        raise AssertionError("transcribe_audio should not be called for no speech")

    def fake_build_worker_debug_cut(*_args, **_kwargs):
        return (
            VadAnalysis(
                is_speech=False,
                speech_ms=0,
                speech_ratio=0.0,
                speech_intervals=[],
            ),
            type(
                "WorkerCut",
                (),
                {
                    "original_duration_ms": 1000,
                    "retained_duration_ms": 1000,
                    "speech_duration_ms": 0,
                    "speech_ratio": 0.0,
                    "retained_intervals": [VadInterval(start_ms=0, end_ms=1000)],
                    "removable_silences": [],
                    "speech_intervals": [],
                    "trim_applied": False,
                },
            )(),
            b"trimmed-audio",
        )

    monkeypatch.setattr("app.main.decode_audio_to_float32_pcm", lambda _audio: b"pcm")
    monkeypatch.setattr("app.main.build_worker_debug_cut", fake_build_worker_debug_cut)
    monkeypatch.setattr("app.main.transcribe_audio", fail_transcribe_audio)

    response = client.post(
        "/api/v1/dev/transcription/debug",
        files={"file": ("sample.webm", b"audio-bytes", "audio/webm")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == ""
    assert payload["vad_decision"] == "no_speech"
    assert payload["worker_input"]["input_byte_size"] == len(b"audio-bytes")


def test_debug_transcription_endpoint_supports_vad_only_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_transcribe_audio(**_kwargs) -> str:
        raise AssertionError("transcribe_audio should not be called for vad_only")

    def fake_build_worker_debug_cut(*_args, **_kwargs):
        return (
            VadAnalysis(
                is_speech=True,
                speech_ms=2200,
                speech_ratio=0.55,
                speech_intervals=[VadInterval(start_ms=50, end_ms=2250)],
            ),
            type(
                "WorkerCut",
                (),
                {
                    "original_duration_ms": 4000,
                    "retained_duration_ms": 3000,
                    "speech_duration_ms": 2200,
                    "speech_ratio": 0.55,
                    "retained_intervals": [VadInterval(start_ms=0, end_ms=3000)],
                    "removable_silences": [VadInterval(start_ms=3000, end_ms=4000)],
                    "speech_intervals": [VadInterval(start_ms=50, end_ms=2250)],
                    "trim_applied": True,
                },
            )(),
            b"trimmed-audio",
        )

    monkeypatch.setattr("app.main.decode_audio_to_float32_pcm", lambda _audio: b"pcm")
    monkeypatch.setattr("app.main.build_worker_debug_cut", fake_build_worker_debug_cut)
    monkeypatch.setattr("app.main.transcribe_audio", fail_transcribe_audio)

    response = client.post(
        "/api/v1/dev/transcription/debug",
        files={"file": ("sample.webm", b"audio-bytes", "audio/webm")},
        data={"mode": "vad_only", "provider": "google_genai", "model": "gemini-2.5-flash"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["mode"] == "vad_only"
    assert payload["transcript"] == ""
    assert payload["vad_decision"] == "speech"
    assert payload["worker_input"]["trimmed_audio_byte_size"] == len(b"trimmed-audio")


def test_debug_trimmed_audio_returns_worker_preview_wav_bytes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_preview = b"worker-preview-wav"

    def fake_build_worker_debug_cut(*_args, **_kwargs):
        return (
            VadAnalysis(
                is_speech=True,
                speech_ms=900,
                speech_ratio=0.5,
                speech_intervals=[VadInterval(start_ms=0, end_ms=900)],
            ),
            type(
                "WorkerCut",
                (),
                {
                    "original_duration_ms": 2000,
                    "retained_duration_ms": 900,
                    "speech_duration_ms": 900,
                    "speech_ratio": 0.5,
                    "retained_intervals": [VadInterval(start_ms=0, end_ms=900)],
                    "removable_silences": [VadInterval(start_ms=900, end_ms=2000)],
                    "speech_intervals": [VadInterval(start_ms=0, end_ms=900)],
                    "trim_applied": True,
                },
            )(),
            expected_preview,
        )

    monkeypatch.setattr("app.main.decode_audio_to_float32_pcm", lambda _audio: b"pcm")
    monkeypatch.setattr("app.main.build_worker_debug_cut", fake_build_worker_debug_cut)

    response = client.post(
        "/api/v1/dev/transcription/debug/trimmed-audio",
        files={"file": ("sample.webm", b"audio-bytes", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.content == expected_preview
    assert response.headers["content-type"] == "audio/wav"
