from __future__ import annotations

import re
from dataclasses import dataclass, field

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

    def to_debug_dict(self, *, include_thinking: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "content": self.content,
            "thinking_source": self.thinking_source,
            "usage": self.usage,
            "request_params": self.request_params,
        }
        if include_thinking:
            payload["thinking"] = self.thinking
        elif self.thinking:
            payload["thinking_chars"] = len(self.thinking)
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

    for item in output:
        item_type = getattr(item, "type", None)
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
        for block in blocks:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                content_parts.append(text.strip())

    thinking = "\n\n".join(thinking_parts) if thinking_parts else None
    content = "\n\n".join(content_parts)
    thinking_source = "openai.responses.reasoning.summary" if thinking else None

    if not content.strip():
        raise ValueError("ai_pipeline_openai_empty_response")

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

    summary: dict[str, object] = {
        "batch_count": len(responses),
        "batches_with_thinking": batches_with_thinking,
    }
    if total_reasoning_tokens:
        summary["total_reasoning_tokens"] = total_reasoning_tokens
    if request_params:
        summary["request_params"] = request_params
    return summary
