from __future__ import annotations

import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class LlmCallTiming:
    time_to_first_token_ms: int | None
    thinking_time_ms: int | None
    output_time_ms: int | None
    total_ms: int
    streamed: bool = False
    estimated: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def elapsed_ms(started_at: float, finished_at: float) -> int:
    return max(0, int(round((finished_at - started_at) * 1000)))


class StreamTimingCollector:
    def __init__(self, *, started_at: float | None = None) -> None:
        self._started_at = started_at if started_at is not None else time.perf_counter()
        self._first_token_at: float | None = None
        self._first_reasoning_at: float | None = None
        self._last_reasoning_at: float | None = None
        self._first_output_at: float | None = None

    def note_reasoning_delta(self, *, at: float | None = None) -> None:
        now = at if at is not None else time.perf_counter()
        if self._first_token_at is None:
            self._first_token_at = now
        if self._first_reasoning_at is None:
            self._first_reasoning_at = now
        self._last_reasoning_at = now

    def note_output_delta(self, *, at: float | None = None) -> None:
        now = at if at is not None else time.perf_counter()
        if self._first_token_at is None:
            self._first_token_at = now
        if self._first_output_at is None:
            self._first_output_at = now

    def build(self, *, finished_at: float | None = None) -> LlmCallTiming:
        ended_at = finished_at if finished_at is not None else time.perf_counter()
        total_ms = elapsed_ms(self._started_at, ended_at)
        ttft = (
            elapsed_ms(self._started_at, self._first_token_at)
            if self._first_token_at is not None
            else None
        )

        thinking_ms: int | None = None
        output_ms: int | None = None

        if self._first_reasoning_at is not None:
            if self._first_output_at is not None:
                thinking_ms = elapsed_ms(self._first_reasoning_at, self._first_output_at)
            elif self._last_reasoning_at is not None:
                thinking_ms = elapsed_ms(self._first_reasoning_at, self._last_reasoning_at)

        if self._first_output_at is not None:
            output_ms = elapsed_ms(self._first_output_at, ended_at)
        elif self._first_token_at is not None and self._first_reasoning_at is None:
            output_ms = elapsed_ms(self._first_token_at, ended_at)

        return LlmCallTiming(
            time_to_first_token_ms=ttft,
            thinking_time_ms=thinking_ms,
            output_time_ms=output_ms,
            total_ms=total_ms,
            streamed=True,
            estimated=False,
        )


def estimate_timing_from_usage(
    *,
    total_ms: int,
    usage: dict[str, object],
) -> LlmCallTiming:
    from common.llm_response import output_token_breakdown_from_usage

    breakdown = output_token_breakdown_from_usage(usage)
    reasoning_tokens = breakdown.get("reasoning_tokens") or 0
    total_output_tokens = breakdown.get("total_output_tokens") or 0

    thinking_ms: int | None = None
    output_ms: int | None = None
    if (
        isinstance(reasoning_tokens, int)
        and isinstance(total_output_tokens, int)
        and total_output_tokens > 0
        and reasoning_tokens > 0
    ):
        thinking_ms = int(total_ms * reasoning_tokens / total_output_tokens)
        output_ms = max(0, total_ms - thinking_ms)

    return LlmCallTiming(
        time_to_first_token_ms=None,
        thinking_time_ms=thinking_ms,
        output_time_ms=output_ms,
        total_ms=total_ms,
        streamed=False,
        estimated=True,
    )


def attach_timing_if_missing(
    response: object,
    *,
    started_at: float,
    finished_at: float | None = None,
) -> object:
    from common.llm_response import LlmResponse

    if not isinstance(response, LlmResponse):
        return response
    if response.timing is not None:
        return response

    ended_at = finished_at if finished_at is not None else time.perf_counter()
    total_ms = elapsed_ms(started_at, ended_at)
    timing = estimate_timing_from_usage(total_ms=total_ms, usage=response.usage)
    return LlmResponse(
        content=response.content,
        thinking=response.thinking,
        thinking_source=response.thinking_source,
        usage=response.usage,
        request_params=response.request_params,
        timing=timing,
    )


__all__ = [
    "LlmCallTiming",
    "StreamTimingCollector",
    "attach_timing_if_missing",
    "elapsed_ms",
    "estimate_timing_from_usage",
]
