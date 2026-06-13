from __future__ import annotations

import json

from common.llm_response import split_thinking_from_content


def _extract_braced_json_object(raw: str) -> str | None:
    start = raw.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(raw)):
        char = raw[index]
        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return raw[start : index + 1]
    return None


def extract_json_object(raw: str) -> dict[str, object]:
    stripped, _thinking = split_thinking_from_content(raw.strip())
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    candidates = [stripped]
    braced = _extract_braced_json_object(stripped)
    if braced and braced not in candidates:
        candidates.append(braced)

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            raise ValueError("ai_pipeline_llm_response_must_be_object")
        return payload

    if last_error is not None:
        raise last_error
    raise ValueError("ai_pipeline_llm_response_must_be_object")
