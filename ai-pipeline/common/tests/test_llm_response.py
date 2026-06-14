from __future__ import annotations

import pytest

from common.llm_response import (
    LlmResponse,
    build_llm_response_from_message,
    build_llm_response_from_openai_responses,
    output_token_breakdown_from_usage,
    split_thinking_from_content,
    summarize_llm_responses,
)
from common.providers import (
    DEFAULT_GROQ_REASONING_EFFORT_QWEN,
    DEFAULT_GROQ_REASONING_FORMAT_QWEN,
    _groq_model_family,
    _resolve_groq_reasoning_kwargs,
    _resolve_openai_reasoning_effort,
    openai_model_supports_reasoning_effort,
)


class FakeMessage:
    def __init__(
        self,
        *,
        content: str = "",
        reasoning: str | None = None,
    ) -> None:
        self.content = content
        self.reasoning = reasoning


def test_split_thinking_from_content() -> None:
    raw = (
        "cluster a: motivo\n"
        '{"section_ids": []}'
    )
    cleaned, thinking = split_thinking_from_content(raw)
    assert cleaned == raw
    assert thinking is None

    think_open = "<think>"
    think_close = "</think>"
    tagged = (
        f"{think_open}cluster a: motivo{think_close}\n"
        '{"section_ids": []}'
    )
    cleaned_tagged, thinking_tagged = split_thinking_from_content(tagged)
    assert cleaned_tagged == '{"section_ids": []}'
    assert thinking_tagged is not None
    assert "cluster a: motivo" in thinking_tagged


class FakeSummary:
    def __init__(self, text: str) -> None:
        self.text = text
        self.type = "summary_text"


class FakeReasoningItem:
    def __init__(self, *, summary: list[FakeSummary] | None = None) -> None:
        self.type = "reasoning"
        self.summary = summary or []
        self.content = []


class FakeOutputText:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeOutputMessage:
    def __init__(self, text: str) -> None:
        self.type = "message"
        self.content = [FakeOutputText(text)]


class FakeResponsesPayload:
    def __init__(self, *, output: list[object], usage: dict[str, object] | None = None) -> None:
        self.output = output
        self.usage = usage


def test_build_llm_response_from_openai_responses_extracts_summary() -> None:
    response = build_llm_response_from_openai_responses(
        response=FakeResponsesPayload(
            output=[
                FakeReasoningItem(summary=[FakeSummary("plan de seccion")]),
                FakeOutputMessage('{"section_id":"motivo_consulta","content":"texto"}'),
            ],
            usage={"output_tokens_details": {"reasoning_tokens": 12}},
        ),
        request_params={"reasoning_effort": "low"},
    )
    assert "motivo_consulta" in response.content
    assert response.thinking == "plan de seccion"
    assert response.thinking_source == "openai.responses.reasoning.summary"
    assert response.request_params["openai_api"] == "responses"


def test_build_llm_response_from_groq_message_reasoning_field() -> None:
    response = build_llm_response_from_message(
        message=FakeMessage(
            content='{"assignments": []}',
            reasoning="cluster a -> motivo_consulta",
        ),
        usage={"completion_tokens_details": {"reasoning_tokens": 12}},
        request_params={"reasoning_effort": "default"},
        provider="groq",
    )
    assert response.content == '{"assignments": []}'
    assert response.thinking == "cluster a -> motivo_consulta"
    assert response.thinking_source == "message.reasoning"


def test_summarize_llm_responses() -> None:
    summary = summarize_llm_responses(
        [
            LlmResponse(
                content="{}",
                thinking="a",
                usage={"completion_tokens_details": {"reasoning_tokens": 10}},
                request_params={"reasoning_effort": "default"},
            ),
            LlmResponse(
                content="{}",
                thinking="b",
                usage={"completion_tokens_details": {"reasoning_tokens": 5}},
            ),
        ]
    )
    assert summary["batches_with_thinking"] == 2
    assert summary["total_reasoning_tokens"] == 15
    assert summary["request_params"] == {"reasoning_effort": "default"}


def test_groq_model_family_detection() -> None:
    assert _groq_model_family("qwen/qwen3-32b") == "qwen3"
    assert _groq_model_family("openai/gpt-oss-20b") == "gpt-oss"
    assert _groq_model_family("llama-3.3-70b-versatile") is None


def test_resolve_groq_reasoning_kwargs_defaults_for_qwen3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("GROQ_REASONING_FORMAT", raising=False)
    api_kwargs, metadata = _resolve_groq_reasoning_kwargs("qwen/qwen3-32b")
    assert api_kwargs == {
        "reasoning_effort": DEFAULT_GROQ_REASONING_EFFORT_QWEN,
        "reasoning_format": DEFAULT_GROQ_REASONING_FORMAT_QWEN,
    }
    assert metadata["model_family"] == "qwen3"


def test_resolve_groq_reasoning_kwargs_none_for_non_reasoning_model() -> None:
    api_kwargs, metadata = _resolve_groq_reasoning_kwargs("llama-3.3-70b-versatile")
    assert api_kwargs == {}
    assert metadata == {}


def test_openai_model_supports_reasoning_effort() -> None:
    assert openai_model_supports_reasoning_effort("gpt-5.4-mini")
    assert openai_model_supports_reasoning_effort("gpt-5.4")
    assert not openai_model_supports_reasoning_effort("gpt-4o-mini")


def test_resolve_openai_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "high")
    api_kwargs, metadata = _resolve_openai_reasoning_effort("gpt-5.4-mini")
    assert api_kwargs == {"reasoning_effort": "high"}
    assert metadata == {"reasoning_effort": "high"}


def test_output_token_breakdown_from_usage_splits_reasoning() -> None:
    breakdown = output_token_breakdown_from_usage(
        {
            "output_tokens": 120,
            "output_tokens_details": {"reasoning_tokens": 40},
        }
    )
    assert breakdown == {
        "total_output_tokens": 120,
        "reasoning_tokens": 40,
        "visible_output_tokens": 80,
    }


def test_resolve_openai_reasoning_effort_none_skips_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "none")
    api_kwargs, metadata = _resolve_openai_reasoning_effort("gpt-5.4")
    assert api_kwargs == {}
    assert metadata == {}


def test_ensure_openai_json_input_hint_appends_when_missing() -> None:
    from common.providers import _ensure_openai_json_input_hint

    payload = '{"section_id":"motivo_consulta"}'
    hinted = _ensure_openai_json_input_hint(payload)
    assert "json" in hinted.lower()
    assert payload in hinted

    already = "Return JSON with assignments"
    assert _ensure_openai_json_input_hint(already) == already
