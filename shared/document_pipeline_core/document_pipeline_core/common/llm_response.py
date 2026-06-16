from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from document_pipeline_core.common.llm_timing import LlmCallTiming

_THINK_BLOCK_PATTERN = re.compile(
    r"<(?:think(?:ing)?|redacted_thinking)>.*?</(?:think(?:ing)?|redacted_thinking)>",
    flags=re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LlmResponse:
    content: str
    thinking: str | None = None
    thinking_source: str | None = None
    usage: dict[str, object] = field(default_factory=dict)
    request_params: dict[str, object] = field(default_factory=dict)
    timing: LlmCallTiming | None = None

    def to_debug_dict(self, *, include_thinking: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "content": self.content,
            "thinking_source": self.thinking_source,
            "usage": self.usage,
            "request_params": self.request_params,
        }
        if self.timing is not None:
            payload["timing"] = self.timing.to_dict()
        if include_thinking:
            payload["thinking"] = self.thinking
        elif self.thinking:
            payload["thinking_chars"] = len(self.thinking)
        return payload


class OpenAIEmptyResponseError(ValueError):
    def __init__(
        self,
        *,
        partial_content: str | None = None,
        partial_thinking: str | None = None,
        output_item_types: list[str] | None = None,
        message_statuses: list[str] | None = None,
        response_status: str | None = None,
        response_error: dict[str, object] | None = None,
        response_incomplete_details: dict[str, object] | None = None,
    ) -> None:
        super().__init__("ai_pipeline_openai_empty_response")
        self.partial_content = partial_content
        self.partial_thinking = partial_thinking
        self.output_item_types = list(output_item_types or [])
        self.message_statuses = list(message_statuses or [])
        self.response_status = response_status
        self.response_error = dict(response_error or {})
        self.response_incomplete_details = dict(response_incomplete_details or {})

    def diagnostics(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.partial_content:
            payload["partial_response"] = self.partial_content
        if self.partial_thinking:
            payload["partial_thinking"] = self.partial_thinking
        if self.output_item_types:
            payload["response_output_item_types"] = self.output_item_types
        if self.message_statuses:
            payload["response_message_statuses"] = self.message_statuses
        if self.response_status:
            payload["response_status"] = self.response_status
        if self.response_error:
            payload["response_error"] = self.response_error
        if self.response_incomplete_details:
            payload["response_incomplete_details"] = (
                self.response_incomplete_details
            )
        return payload


def split_thinking_from_content(raw: str) -> tuple[str, str | None]:
    matches = list(_THINK_BLOCK_PATTERN.finditer(raw))
    if not matches:
        return raw, None
    thinking_parts = [match.group(0) for match in matches]
    cleaned = _THINK_BLOCK_PATTERN.sub("", raw).strip()
    thinking = "\n\n".join(part.strip() for part in thinking_parts if part.strip())
    return cleaned, thinking or None


def normalize_usage(usage: object | None) -> dict[str, object]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    if hasattr(usage, "model_dump"):
        dumped = usage.model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _normalize_model_dict(value: object | None) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    return {"value": str(value)}


def extract_message_thinking(message: object) -> tuple[str | None, str | None]:
    for attr, source in (
        ("reasoning", "message.reasoning"),
        ("reasoning_content", "message.reasoning_content"),
    ):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip(), source

    if hasattr(message, "model_dump"):
        dumped = message.model_dump()
        if isinstance(dumped, dict):
            for key, source in (
                ("reasoning", "message.reasoning"),
                ("reasoning_content", "message.reasoning_content"),
            ):
                value = dumped.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip(), source

    return None, None


def build_llm_response_from_openai_responses(
    *,
    response: object,
    request_params: dict[str, object] | None = None,
) -> LlmResponse:
    output = getattr(response, "output", None) or []
    thinking_parts: list[str] = []
    content_parts: list[str] = []
    output_item_types: list[str] = []
    message_statuses: list[str] = []

    for item in output:
        item_type = getattr(item, "type", None)
        if isinstance(item_type, str) and item_type:
            output_item_types.append(item_type)
        if item_type == "reasoning":
            summary = getattr(item, "summary", None) or []
            for part in summary:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text.strip():
                    thinking_parts.append(text.strip())
            reasoning_content = getattr(item, "content", None) or []
            for block in reasoning_content:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text.strip():
                    thinking_parts.append(text.strip())
            continue

        if item_type != "message":
            continue

        blocks = getattr(item, "content", None) or []
        status = getattr(item, "status", None)
        if isinstance(status, str) and status:
            message_statuses.append(status)
        for block in blocks:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                content_parts.append(text.strip())

    thinking = "\n\n".join(thinking_parts) if thinking_parts else None
    content = "\n\n".join(content_parts)
    thinking_source = "openai.responses.reasoning.summary" if thinking else None

    if not content.strip():
        raise OpenAIEmptyResponseError(
            partial_content=None,
            partial_thinking=thinking,
            output_item_types=output_item_types,
            message_statuses=message_statuses,
            response_status=(
                getattr(response, "status", None)
                if isinstance(getattr(response, "status", None), str)
                else None
            ),
            response_error=_normalize_model_dict(getattr(response, "error", None)),
            response_incomplete_details=_normalize_model_dict(
                getattr(response, "incomplete_details", None)
            ),
        )

    merged_params = dict(request_params or {})
    merged_params["openai_api"] = "responses"

    return LlmResponse(
        content=content,
        thinking=thinking,
        thinking_source=thinking_source,
        usage=normalize_usage(getattr(response, "usage", None)),
        request_params=merged_params,
    )


def build_llm_response_from_message(
    *,
    message: object,
    usage: object | None = None,
    request_params: dict[str, object] | None = None,
    provider: str,
) -> LlmResponse:
    content = getattr(message, "content", None) or ""
    if not isinstance(content, str):
        content = str(content)

    thinking, thinking_source = extract_message_thinking(message)
    if not thinking and content:
        cleaned_content, embedded_thinking = split_thinking_from_content(content)
        if embedded_thinking:
            content = cleaned_content
            thinking = embedded_thinking
            thinking_source = f"{provider}.content.thinking_tags"

    if not content.strip():
        raise ValueError(f"ai_pipeline_{provider}_empty_response")

    return LlmResponse(
        content=content,
        thinking=thinking,
        thinking_source=thinking_source,
        usage=normalize_usage(usage),
        request_params=dict(request_params or {}),
    )


def reasoning_tokens_from_usage(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    for details_key in ("completion_tokens_details", "output_tokens_details"):
        details = usage.get(details_key)
        if not isinstance(details, dict):
            continue
        reasoning_tokens = details.get("reasoning_tokens")
        if isinstance(reasoning_tokens, int):
            return max(0, reasoning_tokens)
    return None


def output_token_breakdown_from_usage(usage: object) -> dict[str, int | None]:
    if not isinstance(usage, dict):
        return {
            "total_output_tokens": None,
            "reasoning_tokens": None,
            "visible_output_tokens": None,
        }

    total_output_tokens: int | None = None
    for key in ("output_tokens", "completion_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            total_output_tokens = max(0, value)
            break

    reasoning_tokens = reasoning_tokens_from_usage(usage)
    visible_output_tokens = None
    if total_output_tokens is not None:
        visible_output_tokens = max(0, total_output_tokens - (reasoning_tokens or 0))

    return {
        "total_output_tokens": total_output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "visible_output_tokens": visible_output_tokens,
    }


def summarize_llm_responses(responses: list[LlmResponse]) -> dict[str, object]:
    total_reasoning_tokens = 0
    batches_with_thinking = 0
    request_params: dict[str, object] = {}

    for response in responses:
        if response.thinking:
            batches_with_thinking += 1
        if response.request_params and not request_params:
            request_params = dict(response.request_params)

        completion_details = response.usage.get("completion_tokens_details")
        if isinstance(completion_details, dict):
            reasoning_tokens = completion_details.get("reasoning_tokens")
            if isinstance(reasoning_tokens, int):
                total_reasoning_tokens += reasoning_tokens
                continue
        output_details = response.usage.get("output_tokens_details")
        if isinstance(output_details, dict):
            reasoning_tokens = output_details.get("reasoning_tokens")
            if isinstance(reasoning_tokens, int):
                total_reasoning_tokens += reasoning_tokens

    summary: dict[str, object] = {
        "batch_count": len(responses),
        "batches_with_thinking": batches_with_thinking,
    }
    if total_reasoning_tokens:
        summary["total_reasoning_tokens"] = total_reasoning_tokens
    if request_params:
        summary["request_params"] = request_params
    return summary
