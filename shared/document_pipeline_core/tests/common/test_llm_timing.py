from __future__ import annotations

from types import SimpleNamespace

from document_pipeline_core.common.llm_timing import StreamTimingCollector, estimate_timing_from_usage
from document_pipeline_core.common.stream_timing import _consume_chat_completion_stream


def test_stream_timing_collector_splits_reasoning_and_output() -> None:
    collector = StreamTimingCollector(started_at=0.0)
    collector.note_reasoning_delta(at=0.1)
    collector.note_reasoning_delta(at=0.3)
    collector.note_output_delta(at=0.5)
    timing = collector.build(finished_at=1.0)

    assert timing.streamed is True
    assert timing.time_to_first_token_ms == 100
    assert timing.thinking_time_ms == 400
    assert timing.output_time_ms == 500
    assert timing.total_ms == 1000


def test_estimate_timing_from_usage_splits_by_token_ratio() -> None:
    timing = estimate_timing_from_usage(
        total_ms=1000,
        usage={
            "output_tokens": 100,
            "output_tokens_details": {"reasoning_tokens": 25},
        },
    )
    assert timing.estimated is True
    assert timing.thinking_time_ms == 250
    assert timing.output_time_ms == 750
    assert timing.time_to_first_token_ms is None


def test_consume_chat_completion_stream_requests_include_usage() -> None:
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content='{"ok": true}', reasoning=None)
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[],
            usage={
                "completion_tokens": 42,
                "prompt_tokens": 100,
                "total_tokens": 142,
            },
        ),
    ]

    class FakeCompletions:
        def create(self, **kwargs: object):
            assert kwargs.get("stream_options") == {"include_usage": True}
            return iter(chunks)

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    response = _consume_chat_completion_stream(
        client=client,
        kwargs={"model": "gpt-5.4-nano"},
        request_metadata={},
        provider="openai",
    )
    assert response.usage["completion_tokens"] == 42
    assert response.usage["prompt_tokens"] == 100
