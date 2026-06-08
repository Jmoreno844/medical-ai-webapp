from __future__ import annotations

from types import SimpleNamespace

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
        return (
            '{"turns":[{"speaker":"PACIENTE","text":"Paciente refiere dolor.",'
            '"overlaps_previous":false,"overlaps_next":false}]}'
        )

    monkeypatch.setattr(gemini, "_transcribe_with_google", fake_google)

    settings = Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai")
    result = await gemini.transcribe_audio(
        gcs_uri="gs://bucket/file.ogg",
        content_type="audio/ogg",
        settings=settings,
    )

    assert len(result) == 1
    assert result[0].text == "Paciente refiere dolor."
    assert captured["gcs_uri"] == "gs://bucket/file.ogg"
    assert captured["audio_bytes"] is None


@pytest.mark.asyncio
async def test_transcribe_audio_routes_to_google_with_inline_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_google(**kwargs) -> str:
        captured.update(kwargs)
        return (
            '{"turns":[{"speaker":"MEDICO","text":"Buenos dias",'
            '"overlaps_previous":false,"overlaps_next":false}]}'
        )

    monkeypatch.setattr(gemini, "_transcribe_with_google", fake_google)

    settings = Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai")
    result = await gemini.transcribe_audio(
        gcs_uri=None,
        content_type="audio/wav",
        settings=settings,
        audio_bytes=b"abc",
    )

    assert result[0].speaker == "MEDICO"
    assert captured["gcs_uri"] is None
    assert captured["audio_bytes"] == b"abc"


@pytest.mark.asyncio
async def test_transcribe_audio_merges_consecutive_same_speaker_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_google(**_kwargs) -> str:
        return (
            '{"turns":['
            '{"speaker":"MEDICO","text":"Primera parte.","overlaps_previous":false,"overlaps_next":false},'
            '{"speaker":"MEDICO","text":"Segunda parte.","overlaps_previous":false,"overlaps_next":false}'
            ']}'
        )

    monkeypatch.setattr(gemini, "_transcribe_with_google", fake_google)

    settings = Settings(ENVIRONMENT="test", TRANSCRIPTION_PROVIDER="google_genai")
    result = await gemini.transcribe_audio(
        gcs_uri="gs://bucket/file.ogg",
        content_type="audio/ogg",
        settings=settings,
    )

    assert len(result) == 1
    assert result[0].text == "Primera parte. Segunda parte."


def test_effective_transcription_model_prefers_explicit_override() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="google_genai",
        TRANSCRIPTION_MODEL="gemini-2.5-flash",
    )

    assert settings.effective_transcription_model == "gemini-2.5-flash"


def test_local_debug_logs_gemini_json_response(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(ENVIRONMENT="local", TRANSCRIPTION_PROVIDER="google_genai")
    raw_json = (
        '{"turns":[{"speaker":"PACIENTE","text":"Hola","overlaps_previous":false,'
        '"overlaps_next":false}]}'
    )

    with caplog.at_level("INFO"):
        gemini._log_gemini_response_for_local_debug(
            settings,
            raw_text=raw_json,
            model="gemini-2.5-flash",
        )

    assert any(
        "Gemini transcription response (local debug" in record.message
        for record in caplog.records
    )
    assert any('"speaker": "PACIENTE"' in record.message for record in caplog.records)


def test_local_debug_skips_logging_outside_local(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(ENVIRONMENT="production", TRANSCRIPTION_PROVIDER="google_genai")

    with caplog.at_level("INFO"):
        gemini._log_gemini_response_for_local_debug(
            settings,
            raw_text='{"turns":[]}',
            model="gemini-2.5-flash",
        )

    assert caplog.records == []


@pytest.mark.asyncio
async def test_google_transcription_config_disables_thinking_and_uses_token_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        async def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text='{"turns":[]}',
                candidates=[],
                usage_metadata=None,
            )

    fake_client = SimpleNamespace(aio=SimpleNamespace(models=FakeModels()))
    monkeypatch.setattr(gemini, "_get_google_client", lambda *_args: fake_client)

    settings = Settings(
        ENVIRONMENT="test",
        GCP_PROJECT_ID="test-project",
        TRANSCRIPTION_PROVIDER="google_genai",
        TRANSCRIPTION_GEMINI_MAX_OUTPUT_TOKENS=4096,
    )

    raw_text = await gemini._transcribe_with_google(
        gcs_uri="gs://bucket/file.ogg",
        content_type="audio/ogg",
        settings=settings,
    )

    assert raw_text == '{"turns":[]}'
    config = captured["config"]
    assert config.max_output_tokens == 4096
    assert config.thinking_config.thinking_budget == 0


def test_gemini_metadata_log_includes_safe_finish_and_usage_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=20,
            thoughts_token_count=0,
            total_token_count=30,
        ),
    )

    with caplog.at_level("INFO"):
        gemini._log_gemini_response_metadata(response)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.event == "gemini_response_metadata"
    assert record.finish_reason == "STOP"
    assert record.prompt_token_count == 10
    assert record.candidates_token_count == 20
    assert record.thoughts_token_count == 0
    assert record.total_token_count == 30
    assert "turns" not in record.message


def test_unsupported_provider_normalizes_to_google_genai() -> None:
    settings = Settings(
        ENVIRONMENT="test",
        TRANSCRIPTION_PROVIDER="legacy_provider",
    )

    assert settings.transcription_provider_name == "google_genai"
    assert settings.effective_transcription_model == "gemini-2.5-flash"
