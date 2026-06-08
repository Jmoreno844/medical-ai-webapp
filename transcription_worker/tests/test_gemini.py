from __future__ import annotations

import pytest

from app import gemini
from app.settings import Settings


@pytest.mark.asyncio
async def test_transcribe_audio_routes_to_google_with_gcs_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_google(**kwargs) -> str:
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(gemini, "_transcribe_with_google", fake_google)

    settings = Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai")
    result = await gemini.transcribe_audio(
        gcs_uri="gs://bucket/file.ogg",
        content_type="audio/ogg",
        settings=settings,
    )

    assert result == "ok"
    assert captured["gcs_uri"] == "gs://bucket/file.ogg"
    assert captured["audio_bytes"] is None


@pytest.mark.asyncio
async def test_transcribe_audio_routes_to_google_with_inline_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_google(**kwargs) -> str:
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(gemini, "_transcribe_with_google", fake_google)

    settings = Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai")
    result = await gemini.transcribe_audio(
        gcs_uri=None,
        content_type="audio/wav",
        settings=settings,
        audio_bytes=b"abc",
    )

    assert result == "ok"
    assert captured["gcs_uri"] is None
    assert captured["audio_bytes"] == b"abc"


def test_effective_transcription_model_prefers_explicit_override() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="google_genai",
        TRANSCRIPTION_MODEL="gemini-2.5-flash",
    )

    assert settings.effective_transcription_model == "gemini-2.5-flash"


def test_unsupported_provider_normalizes_to_google_genai() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="legacy_provider",
    )

    assert settings.transcription_provider_name == "google_genai"
    assert settings.effective_transcription_model == "gemini-2.5-flash"


def test_strip_prompt_echo_keeps_transcript_prefix() -> None:
    raw = (
        "Paciente Alejandra Huaman Kruger. "
        f"{gemini.SECTION_TRANSCRIPTION_PROMPT}"
    )

    assert gemini._strip_prompt_echo(raw) == "Paciente Alejandra Huaman Kruger."


def test_strip_prompt_echo_returns_empty_for_prompt_only() -> None:
    assert gemini._strip_prompt_echo(gemini.SECTION_TRANSCRIPTION_PROMPT) == ""
