from __future__ import annotations

import pytest

from common.llm_response import LlmResponse
from generation.generate import call_generation_llm_detailed


def test_call_generation_llm_retries_openai_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import generation.generate as generate_module

    calls = 0

    def fake_call_llm_detailed(**_kwargs: object) -> LlmResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("ai_pipeline_openai_empty_response")
        return LlmResponse(
            content='{"section_id":"motivo_consulta","content":"ok"}',
            request_params={"openai_api": "responses"},
        )

    monkeypatch.setattr(generate_module, "call_llm_detailed", fake_call_llm_detailed)

    response = call_generation_llm_detailed(
        provider="openai",
        model="gpt-test",
        system="system",
        user="user",
    )

    assert calls == 2
    assert response.request_params["retry_count"] == 1
    assert "ok" in response.content


def test_call_generation_llm_does_not_retry_non_openai_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import generation.generate as generate_module

    calls = 0

    def fake_call_llm_detailed(**_kwargs: object) -> LlmResponse:
        nonlocal calls
        calls += 1
        raise ValueError("ai_pipeline_openai_empty_response")

    monkeypatch.setattr(generate_module, "call_llm_detailed", fake_call_llm_detailed)

    with pytest.raises(ValueError, match="ai_pipeline_openai_empty_response"):
        call_generation_llm_detailed(
            provider="groq",
            model="gpt-test",
            system="system",
            user="user",
        )

    assert calls == 1
