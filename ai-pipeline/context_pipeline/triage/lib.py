from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import DoctorItem, TriageResult, audit_triage_result
from common.json_utils import extract_json_object
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "triage"


def triage_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_triage_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return triage_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_triage_prompt(version)


def render_triage_payload(
    *,
    session_id: str,
    items: list[DoctorItem],
) -> str:
    if not items:
        raise ValueError("triage_payload_requires_at_least_one_item")
    payload = {
        "session_id": session_id,
        "items": [{"id": item.id, "text": item.text} for item in items],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_triage_result(raw: str) -> TriageResult:
    payload = extract_json_object(raw)
    try:
        return TriageResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"triage_invalid_result: {exc}") from exc


def enrich_triage_result_for_export(
    result: TriageResult,
    *,
    items: list[DoctorItem],
) -> dict[str, object]:
    items_by_id = {item.id: item.text for item in items}
    return {
        "directives": [directive.model_dump(mode="json") for directive in result.directives],
        "content_ids": list(result.content_ids),
        "drop_ids": list(result.drop_ids),
        "content_items": [
            {"id": item_id, "text": items_by_id.get(item_id, "")}
            for item_id in result.content_ids
        ],
        "dropped_items": [
            {"id": item_id, "text": items_by_id.get(item_id, "")}
            for item_id in result.drop_ids
        ],
    }


__all__ = [
    "MODULE_ROOT",
    "enrich_triage_result_for_export",
    "load_prompt",
    "load_triage_prompt",
    "parse_triage_result",
    "prompt_file_path",
    "render_triage_payload",
    "triage_prompt_file_path",
]
