from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app import gemini
from app.settings import Settings


async def _yield_chunks(*chunks: str) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_stream_document_generation_uses_google_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[tuple[str, str]] = []

    async def fake_google(*, prompt: str, settings: Settings) -> AsyncIterator[str]:
        called.append((prompt, settings.document_generation_provider_name))
        async for chunk in _yield_chunks("hola"):
            yield chunk

    monkeypatch.setattr(gemini, "_stream_with_google", fake_google)

    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DOCUMENT_GENERATION_PROVIDER="google_genai",
    )
    result = [
        chunk
        async for chunk in gemini.stream_document_generation(
            prompt="ping",
            settings=settings,
        )
    ]

    assert result == ["hola"]
    assert called == [("ping", "google_genai")]


@pytest.mark.asyncio
async def test_stream_document_generation_uses_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[tuple[str, str]] = []

    async def fake_anthropic(
        *,
        prompt: str,
        settings: Settings,
    ) -> AsyncIterator[str]:
        called.append((prompt, settings.document_generation_provider_name))
        async for chunk in _yield_chunks("claude"):
            yield chunk

    monkeypatch.setattr(gemini, "_stream_with_anthropic", fake_anthropic)

    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DOCUMENT_GENERATION_PROVIDER="anthropic_vertex",
        DOCUMENT_GENERATION_MODEL="claude-3-5-sonnet-v2@20241022",
    )
    result = [
        chunk
        async for chunk in gemini.stream_document_generation(
            prompt="ping",
            settings=settings,
        )
    ]

    assert result == ["claude"]
    assert called == [("ping", "anthropic_vertex")]


def test_settings_effective_model_prefers_document_generation_model() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DOCUMENT_GENERATION_MODEL="claude-3-5-sonnet-v2@20241022",
        DOCUMENT_GENERATION_GEMINI_MODEL="gemini-3-flash-preview",
    )

    assert settings.effective_document_generation_model == (
        "claude-3-5-sonnet-v2@20241022"
    )


def test_settings_effective_model_falls_back_to_legacy_gemini_field() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DOCUMENT_GENERATION_PROVIDER="google_genai",
        DOCUMENT_GENERATION_GEMINI_MODEL="gemini-3-flash-preview",
    )

    assert settings.effective_document_generation_model == "gemini-3-flash-preview"
