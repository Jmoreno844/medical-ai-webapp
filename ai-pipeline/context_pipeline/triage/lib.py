from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import DoctorItem, TriageResult, audit_triage_result
from common.json_utils import extract_json_object
from common.prompt_registry import load_py_prompt_module
from common.prompt_runtime import (
    build_output_schema,
    load_system_prompt,
    prompt_reference as runtime_prompt_reference,
    structured_output_enabled,
    uses_py_prompt,
)
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "triage"
PY_TRIAGE_STEP = "context_triage"
PY_TRIAGE_PROMPT_VERSIONS = frozenset({"v001"})


def triage_uses_py_prompt(prompt_version: str) -> bool:
    return uses_py_prompt(PY_TRIAGE_STEP, prompt_version)


def triage_structured_output_enabled(prompt_version: str) -> bool:
    return structured_output_enabled(PY_TRIAGE_STEP, prompt_version)


def triage_output_schema(
    items: list[DoctorItem],
    *,
    prompt_version: str,
) -> dict[str, object] | None:
    return build_output_schema(
        PY_TRIAGE_STEP,
        prompt_version,
        item_ids=[item.id for item in items],
    )


def triage_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_triage_prompt(version: str) -> str:
    return load_system_prompt(PY_TRIAGE_STEP, version)


def triage_prompt_reference(version: str) -> str:
    return runtime_prompt_reference(PY_TRIAGE_STEP, version)


def prompt_file_path(version: str) -> Path:
    return triage_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_triage_prompt(version)


def _items_for_model_payload(items: list[DoctorItem]) -> list[dict[str, object]]:
    return [
        {"id": int(item.id), "text": item.text}
        for item in items
    ]


def render_triage_payload(
    *,
    session_id: str,
    items: list[DoctorItem],
    prompt_version: str = "v001",
    available_documents: list[str] | None = None,
    template_section_ids: list[str] | None = None,
) -> str:
    if not items:
        raise ValueError("triage_payload_requires_at_least_one_item")
    if triage_uses_py_prompt(prompt_version):
        module = load_py_prompt_module(PY_TRIAGE_STEP, prompt_version)
        return module.render_user_payload(
            session_id=session_id,
            items=_items_for_model_payload(items),
            available_documents=available_documents,
            template_section_ids=template_section_ids,
        )
    payload = {
        "session_id": session_id,
        "manifest": {
            "available_documents": list(available_documents or []),
            "template_section_ids": list(template_section_ids or []),
        },
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
    "PY_TRIAGE_PROMPT_VERSIONS",
    "PY_TRIAGE_STEP",
    "enrich_triage_result_for_export",
    "load_prompt",
    "load_triage_prompt",
    "parse_triage_result",
    "prompt_file_path",
    "render_triage_payload",
    "triage_output_schema",
    "triage_prompt_file_path",
    "triage_prompt_reference",
    "triage_structured_output_enabled",
    "triage_uses_py_prompt",
]
