from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from common.json_utils import extract_json_object
from common.output_detail import DEFAULT_OUTPUT_DETAIL
from common.prompts import (
    DEFAULT_PROMPT_VERSION,
)
from common.prompts import (
    load_prompt as load_prompt_from_file,
)
from common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)
from common.case_paths import TRANSCRIPT_CASES_INDEX
from common.transcripts import TranscriptCase

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "filtering"
DEFAULT_CASES_INDEX = TRANSCRIPT_CASES_INDEX

FilteringCase = TranscriptCase


class FilteringResult(BaseModel):
    drop_turn_ids: list[int] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DropAudit:
    expected_turn_ids: list[int]
    drop_turn_ids: list[int]
    extra_turn_ids: list[int]
    duplicate_turn_ids: list[int]

    @property
    def is_valid(self) -> bool:
        return not self.extra_turn_ids and not self.duplicate_turn_ids

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "expected_turn_count": len(self.expected_turn_ids),
            "drop_count": len(set(self.drop_turn_ids)),
            "extra_turn_ids": self.extra_turn_ids,
            "duplicate_turn_ids": self.duplicate_turn_ids,
        }


def filtering_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_filtering_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return filtering_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_filtering_prompt(version)


def parse_filtering_result(raw: str) -> FilteringResult:
    payload = extract_json_object(raw)
    try:
        return FilteringResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(
            f"filtering_invalid_result: {exc}"
        ) from exc


def audit_drop_turn_ids(
    result: FilteringResult,
    catalog: list[dict[str, object]],
) -> DropAudit:
    expected_turn_ids = [int(item["turn_id"]) for item in catalog]
    expected_set = set(expected_turn_ids)
    drop_turn_ids = result.drop_turn_ids

    seen: set[int] = set()
    duplicate_turn_ids: list[int] = []
    for turn_id in drop_turn_ids:
        if turn_id in seen and turn_id not in duplicate_turn_ids:
            duplicate_turn_ids.append(turn_id)
        seen.add(turn_id)

    drop_set = set(drop_turn_ids)
    extra_turn_ids = sorted(drop_set - expected_set)
    return DropAudit(
        expected_turn_ids=expected_turn_ids,
        drop_turn_ids=drop_turn_ids,
        extra_turn_ids=extra_turn_ids,
        duplicate_turn_ids=sorted(duplicate_turn_ids),
    )


def expand_filtering_decisions(
    result: FilteringResult,
    catalog: list[dict[str, object]],
) -> dict[str, object]:
    drop_set = set(result.drop_turn_ids)
    keep_turn_ids: list[int] = []
    decisions: list[dict[str, object]] = []
    for item in catalog:
        turn_id = int(item["turn_id"])
        keep = 0 if turn_id in drop_set else 1
        if keep:
            keep_turn_ids.append(turn_id)
        decisions.append(
            {
                "turn_id": turn_id,
                "keep": keep,
                "speaker": item["speaker"],
                "text": item["text"],
            }
        )
    drop_count = len(drop_set)
    keep_count = len(keep_turn_ids)
    return {
        "drop_turn_ids": sorted(drop_set),
        "keep_turn_ids": keep_turn_ids,
        "decisions": decisions,
        "drop_count": drop_count,
        "keep_count": keep_count,
    }


def enrich_filtering_result_for_export(
    result: FilteringResult,
    catalog: list[dict[str, object]],
) -> dict[str, object]:
    return expand_filtering_decisions(result, catalog)


def format_filtering_output_for_detail(
    output: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return output
    compact: dict[str, object] = {}
    for key in (
        "model_alias",
        "provider",
        "model",
        "filtering_result",
        "drop_audit",
        "error",
    ):
        if key in output:
            compact[key] = output[key]
    return compact


def format_drop_audit(audit: DropAudit) -> str:
    lines: list[str] = []
    if not audit.is_valid:
        lines.append("WARNING: invalid drop_turn_ids")
    lines.append("drop audit:")
    lines.append(f"  expected turns: {len(audit.expected_turn_ids)}")
    lines.append(f"  dropped: {len(set(audit.drop_turn_ids))}")
    if audit.extra_turn_ids:
        lines.append(f"  extra: {audit.extra_turn_ids}")
    if audit.duplicate_turn_ids:
        lines.append(f"  duplicates: {audit.duplicate_turn_ids}")
    if audit.is_valid:
        lines.append("  status: valid")
    return "\n".join(lines)


def format_debug_output(
    result: FilteringResult,
    catalog: list[dict[str, object]],
) -> str:
    drop_set = set(result.drop_turn_ids)
    turn_by_id = {int(item["turn_id"]): item for item in catalog}
    lines: list[str] = []
    lines.append("DROP turns:")
    if not drop_set:
        lines.append("  (none)")
    else:
        for turn_id in sorted(drop_set):
            turn = turn_by_id.get(turn_id)
            if turn is None:
                lines.append(f"  - {turn_id} (unknown)")
                continue
            preview = str(turn["text"])
            if len(preview) > 120:
                preview = preview[:117] + "..."
            lines.append(f"  - {turn_id} ({turn['speaker']}): {preview}")
    total = len(catalog)
    dropped = len(drop_set)
    kept = total - dropped
    pct = (dropped / total * 100) if total else 0.0
    lines.append("")
    lines.append(f"summary: kept={kept} dropped={dropped} ({pct:.1f}%)")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_CASES_INDEX",
    "DEFAULT_OUTPUT_DETAIL",
    "DEFAULT_PROMPT_VERSION",
    "MODULE_ROOT",
    "DropAudit",
    "FilteringCase",
    "FilteringResult",
    "audit_drop_turn_ids",
    "enrich_filtering_result_for_export",
    "expand_filtering_decisions",
    "format_debug_output",
    "format_drop_audit",
    "format_filtering_output_for_detail",
    "load_prompt",
    "parse_filtering_result",
    "prompt_file_path",
]
