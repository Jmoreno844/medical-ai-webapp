from __future__ import annotations

import pytest

from app import gemini
from app.settings import Settings


@pytest.mark.asyncio
async def test_transcribe_audio_routes_to_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_google(**kwargs) -> str:
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(gemini, "_transcribe_with_google", fake_google)

    settings = Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai")
    result = await gemini.transcribe_audio(
        gcs_uri="gs://bucket/file.webm",
        content_type="audio/webm",
        settings=settings,
    )

    assert result == "ok"
    assert captured["gcs_uri"] == "gs://bucket/file.webm"


@pytest.mark.asyncio
async def test_transcribe_audio_routes_to_openai_and_requires_audio_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_openai(**kwargs) -> str:
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(gemini, "_transcribe_with_openai", fake_openai)

    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="openai",
        TRANSCRIPTION_MODEL="gpt-4o-mini-transcribe",
    )
    result = await gemini.transcribe_audio(
        gcs_uri="gs://bucket/file.webm",
        content_type="audio/webm",
        settings=settings,
        audio_bytes=b"abc",
    )

    assert result == "ok"
    assert captured["audio_bytes"] == b"abc"


def test_effective_transcription_model_uses_openai_default_for_openai_provider() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="openai",
    )

    assert settings.effective_transcription_model == "gpt-4o-mini-transcribe"


def test_effective_transcription_model_prefers_explicit_override() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="google_genai",
        TRANSCRIPTION_MODEL="gemini-2.5-flash",
    )

    assert settings.effective_transcription_model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_openai_provider_requires_api_key() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="openai",
        OPENAI_API_KEY="",
    )

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        await gemini.transcribe_audio(
            gcs_uri="gs://bucket/file.webm",
            content_type="audio/webm",
            settings=settings,
            audio_bytes=b"abc",
        )


def test_filename_for_content_type_normalizes_codec_suffix() -> None:
    assert gemini._filename_for_content_type("audio/webm;codecs=opus") == "section.webm"


def test_strip_prompt_echo_keeps_transcript_prefix() -> None:
    raw = (
        "Paciente Alejandra Huaman Kruger. "
        f"{gemini.SECTION_TRANSCRIPTION_PROMPT}"
    )

    assert gemini._strip_prompt_echo(raw) == "Paciente Alejandra Huaman Kruger."


def test_strip_prompt_echo_returns_empty_for_prompt_only() -> None:
    assert gemini._strip_prompt_echo(gemini.SECTION_TRANSCRIPTION_PROMPT) == ""
