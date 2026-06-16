from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from document_pipeline_core.common.llm_response import (
    LlmResponse,
    build_llm_response_from_message,
    normalize_usage,
)
from document_pipeline_core.common.llm_timing import StreamTimingCollector


def _event_has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _consume_openai_responses_stream(
  *,
  client: Any,
  kwargs: dict[str, object],
  request_metadata: dict[str, object],
) -> LlmResponse:
    from document_pipeline_core.common.llm_response import build_llm_response_from_openai_responses

    collector = StreamTimingCollector()
    with client.responses.stream(**kwargs) as stream:
        for event in stream:
            event_type = getattr(event, "type", "") or ""
            if "reasoning" in event_type and event_type.endswith(".delta"):
                delta = getattr(event, "delta", None)
                if _event_has_text(delta):
                    collector.note_reasoning_delta()
                continue
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if _event_has_text(delta):
                    collector.note_output_delta()
        response = stream.get_final_response()

    llm_response = build_llm_response_from_openai_responses(
        response=response,
        request_params=request_metadata,
    )
    return LlmResponse(
        content=llm_response.content,
        thinking=llm_response.thinking,
        thinking_source=llm_response.thinking_source,
        usage=llm_response.usage,
        request_params=llm_response.request_params,
        timing=collector.build(),
    )


def _consume_chat_completion_stream(
    *,
    client: Any,
    kwargs: dict[str, object],
    request_metadata: dict[str, object],
    provider: str,
) -> LlmResponse:
    collector = StreamTimingCollector()
    stream_kwargs = {
        **kwargs,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    stream = client.chat.completions.create(**stream_kwargs)

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: dict[str, object] = {}

    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = normalize_usage(chunk_usage)
            continue

        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue

        reasoning = getattr(delta, "reasoning", None)
        if _event_has_text(reasoning):
            collector.note_reasoning_delta()
            reasoning_parts.append(str(reasoning))

        content = getattr(delta, "content", None)
        if _event_has_text(content):
            collector.note_output_delta()
            content_parts.append(str(content))

        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            usage = normalize_usage(chunk_usage)

    message = SimpleNamespace(
        content="".join(content_parts),
        reasoning="".join(reasoning_parts) if reasoning_parts else None,
    )
    llm_response = build_llm_response_from_message(
        message=message,
        usage=usage,
        request_params=request_metadata,
        provider=provider,
    )
    return LlmResponse(
        content=llm_response.content,
        thinking=llm_response.thinking,
        thinking_source=llm_response.thinking_source,
        usage=llm_response.usage,
        request_params=llm_response.request_params,
        timing=collector.build(),
    )


def call_with_stream_timing(
    *,
    started_at: float,
    call: Any,
) -> LlmResponse:
    response = call()
    if isinstance(response, LlmResponse) and response.timing is not None:
        return response
    from document_pipeline_core.common.llm_timing import attach_timing_if_missing

    return attach_timing_if_missing(response, started_at=started_at)


__all__ = [
    "_consume_chat_completion_stream",
    "_consume_openai_responses_stream",
    "call_with_stream_timing",
]
