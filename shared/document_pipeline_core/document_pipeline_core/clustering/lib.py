from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from document_pipeline_core.common.json_utils import extract_json_object
from document_pipeline_core.common.output_detail import DEFAULT_OUTPUT_DETAIL
from document_pipeline_core.common.prompts import (
    DEFAULT_PROMPT_VERSION,
)
from document_pipeline_core.common.prompts import (
    load_prompt as load_prompt_from_file,
)
from document_pipeline_core.common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)
from document_pipeline_core.common.case_paths import TRANSCRIPT_CASES_INDEX
from document_pipeline_core.common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_system_prompt
from document_pipeline_core.common.transcripts import TranscriptCase, build_turn_catalog, render_user_payload

CORE_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "clustering"
DEFAULT_CASES_INDEX = TRANSCRIPT_CASES_INDEX

ClusteringCase = TranscriptCase

PY_CLUSTERING_PROMPT_VERSIONS = frozenset({"v002"})


def clustering_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version("clustering", prompt_version)


def clustering_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_CLUSTERING_PROMPT_VERSIONS


def clustering_output_schema(
    catalog: list[dict[str, object]],
    *,
    prompt_version: str,
) -> dict[str, object] | None:
    if not clustering_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module("clustering", prompt_version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(f"clustering_py_prompt_missing_output_schema: {prompt_version}")
    turn_ids = [int(item["turn_id"]) for item in catalog]
    schema = output_schema_fn(turn_ids=turn_ids)
    if not isinstance(schema, dict):
        raise ValueError(f"clustering_py_prompt_invalid_output_schema: {prompt_version}")
    return schema


def render_clustering_user_payload(
    *,
    case: TranscriptCase,
    prompt_version: str,
) -> str:
    catalog = build_turn_catalog(case.transcript_json)
    if clustering_uses_py_prompt(prompt_version):
        module = load_py_prompt_module("clustering", prompt_version)
        return module.render_user_payload(turns=catalog)
    return render_user_payload(case)


def clustering_prompt_reference(version: str) -> str:
    if clustering_uses_py_prompt(version):
        module_path = load_py_prompt_module("clustering", version).__name__
        return f"{module_path.replace('.', '/')}.py"
    return str(clustering_prompt_file_path(version).relative_to(MODULE_ROOT))


class TopicCluster(BaseModel):
    topic_label: str
    turn_ids: list[int] = Field(default_factory=list)


class ClusteringResult(BaseModel):
    clusters: list[TopicCluster] = Field(default_factory=list)
    unassigned_turn_ids: list[int] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TurnCoverageAudit:
    expected_turn_ids: list[int]
    referenced_turn_ids: list[int]
    missing_turn_ids: list[int]
    extra_turn_ids: list[int]
    duplicate_turn_ids: list[int]

    @property
    def is_complete(self) -> bool:
        return (
            not self.missing_turn_ids
            and not self.extra_turn_ids
            and not self.duplicate_turn_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "is_complete": self.is_complete,
            "expected_turn_count": len(self.expected_turn_ids),
            "referenced_turn_count": len(set(self.referenced_turn_ids)),
            "missing_turn_ids": self.missing_turn_ids,
            "extra_turn_ids": self.extra_turn_ids,
            "duplicate_turn_ids": self.duplicate_turn_ids,
        }


def clustering_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_clustering_prompt(version: str) -> str:
    if clustering_uses_py_prompt(version):
        return py_system_prompt("clustering", version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return clustering_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_clustering_prompt(version)


def audit_turn_coverage(
    result: ClusteringResult,
    catalog: list[dict[str, object]],
) -> TurnCoverageAudit:
    expected_turn_ids = [int(item["turn_id"]) for item in catalog]
    expected_set = set(expected_turn_ids)
    referenced_turn_ids: list[int] = []
    for cluster in result.clusters:
        referenced_turn_ids.extend(cluster.turn_ids)
    referenced_turn_ids.extend(result.unassigned_turn_ids)

    seen: set[int] = set()
    duplicate_turn_ids: list[int] = []
    for turn_id in referenced_turn_ids:
        if turn_id in seen and turn_id not in duplicate_turn_ids:
            duplicate_turn_ids.append(turn_id)
        seen.add(turn_id)

    referenced_set = set(referenced_turn_ids)
    missing_turn_ids = sorted(expected_set - referenced_set)
    extra_turn_ids = sorted(referenced_set - expected_set)
    return TurnCoverageAudit(
        expected_turn_ids=expected_turn_ids,
        referenced_turn_ids=referenced_turn_ids,
        missing_turn_ids=missing_turn_ids,
        extra_turn_ids=extra_turn_ids,
        duplicate_turn_ids=sorted(duplicate_turn_ids),
    )


def parse_clustering_result(raw: str) -> ClusteringResult:
    payload = extract_json_object(raw)
    try:
        return ClusteringResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(
            f"clustering_invalid_result: {exc}"
        ) from exc


def _turn_export_item(
    turn_id: int,
    catalog_by_id: dict[int, dict[str, object]],
) -> dict[str, object]:
    turn = catalog_by_id.get(turn_id)
    if turn is None:
        return {"turn_id": turn_id}
    return {
        "turn_id": turn_id,
        "speaker": turn["speaker"],
        "text": turn["text"],
    }


def enrich_clustering_result_for_export(
    result: ClusteringResult,
    catalog: list[dict[str, object]],
) -> dict[str, object]:
    catalog_by_id = {int(item["turn_id"]): item for item in catalog}
    clusters: list[dict[str, object]] = []
    for cluster in result.clusters:
        turns = [
            _turn_export_item(turn_id, catalog_by_id)
            for turn_id in cluster.turn_ids
        ]
        clusters.append(
            {
                "topic_label": cluster.topic_label,
                "turn_ids": cluster.turn_ids,
                "turns": turns,
            }
        )
    unassigned_turns = [
        _turn_export_item(turn_id, catalog_by_id)
        for turn_id in result.unassigned_turn_ids
    ]
    return {
        "clusters": clusters,
        "unassigned_turn_ids": result.unassigned_turn_ids,
        "unassigned_turns": unassigned_turns,
    }


def _compact_thinking_fields(record: dict[str, object]) -> dict[str, object]:
    compact = dict(record)
    thinking = record.get("thinking")
    if isinstance(thinking, str) and thinking:
        compact["thinking"] = thinking
        compact["thinking_chars"] = len(thinking)
    return compact


def format_clustering_repair_pass_for_detail(
    repair_pass: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from document_pipeline_core.common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return repair_pass

    compact_pass: dict[str, object] = {}
    for key in (
        "pass_index",
        "missing_turn_ids_before",
        "assignments",
        "unassigned_turn_ids",
        "still_missing_after",
        "response_time_ms",
        "thinking_source",
        "llm_usage",
        "llm_timing",
    ):
        if key in repair_pass:
            compact_pass[key] = repair_pass[key]
    thinking = repair_pass.get("thinking")
    if isinstance(thinking, str) and thinking:
        compact_pass["thinking"] = thinking
    return _compact_thinking_fields(compact_pass)


def format_clustering_output_for_detail(
    output: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from document_pipeline_core.common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return output

    compact: dict[str, object] = {}
    for key in (
        "model_alias",
        "provider",
        "model",
        "clustering_result",
        "turn_coverage",
        "repair_passes",
        "thinking_source",
        "llm_usage",
        "llm_timing",
        "llm_request_params",
        "error",
    ):
        if key in output:
            compact[key] = output[key]

    thinking = output.get("thinking")
    if isinstance(thinking, str) and thinking:
        compact["thinking"] = thinking
        compact["thinking_chars"] = len(thinking)
    elif "thinking_source" in output:
        compact["thinking_source"] = output["thinking_source"]

    repair_passes = output.get("repair_passes")
    if isinstance(repair_passes, list):
        compact["repair_passes"] = [
            format_clustering_repair_pass_for_detail(repair_pass, output_detail)
            if isinstance(repair_pass, dict)
            else repair_pass
            for repair_pass in repair_passes
        ]

    return compact


def format_turn_coverage_audit(
    audit: TurnCoverageAudit,
    catalog: list[dict[str, object]],
) -> str:
    turn_by_id = {item["turn_id"]: item for item in catalog}
    lines: list[str] = []
    if not audit.is_complete:
        lines.append("WARNING: incomplete turn coverage")
    lines.extend(
        [
            "turn coverage:",
            f"  expected: {len(audit.expected_turn_ids)}",
            f"  referenced: {len(set(audit.referenced_turn_ids))}",
        ]
    )
    if audit.missing_turn_ids:
        lines.append(f"  missing ({len(audit.missing_turn_ids)}):")
        for turn_id in audit.missing_turn_ids:
            turn = turn_by_id.get(turn_id)
            if turn is None:
                lines.append(f"    - {turn_id}")
                continue
            preview = str(turn["text"])
            if len(preview) > 80:
                preview = preview[:77] + "..."
            lines.append(f"    - {turn_id} ({turn['speaker']}): {preview}")
    else:
        lines.append("  missing: none")

    if audit.extra_turn_ids:
        lines.append(f"  extra: {audit.extra_turn_ids}")
    if audit.duplicate_turn_ids:
        lines.append(f"  duplicates: {audit.duplicate_turn_ids}")
    return "\n".join(lines)


def format_debug_output(
    result: ClusteringResult,
    catalog: list[dict[str, object]],
) -> str:
    turn_by_id = {item["turn_id"]: item for item in catalog}
    lines: list[str] = []
    for cluster in result.clusters:
        lines.append(cluster.topic_label)
        for turn_id in cluster.turn_ids:
            turn = turn_by_id.get(turn_id)
            if turn is None:
                lines.append(f"  - {turn_id} (unknown)")
                continue
            preview = str(turn["text"])
            if len(preview) > 120:
                preview = preview[:117] + "..."
            lines.append(f"  - {turn_id} ({turn['speaker']}): {preview}")
        lines.append("")
    if result.unassigned_turn_ids:
        lines.append("unassigned:")
        for turn_id in result.unassigned_turn_ids:
            turn = turn_by_id.get(turn_id)
            if turn is None:
                lines.append(f"  - {turn_id}")
                continue
            text_preview = str(turn["text"])[:80]
            lines.append(f"  - {turn_id} ({turn['speaker']}): {text_preview}")
    return "\n".join(lines).strip()


__all__ = [
    "DEFAULT_CASES_INDEX",
    "DEFAULT_OUTPUT_DETAIL",
    "DEFAULT_PROMPT_VERSION",
    "MODULE_ROOT",
    "ClusteringCase",
    "ClusteringResult",
    "TopicCluster",
    "TurnCoverageAudit",
    "audit_turn_coverage",
    "build_turn_catalog",
    "clustering_output_schema",
    "clustering_prompt_reference",
    "clustering_structured_output_enabled",
    "clustering_uses_py_prompt",
    "enrich_clustering_result_for_export",
    "format_clustering_output_for_detail",
    "format_clustering_repair_pass_for_detail",
    "format_debug_output",
    "format_turn_coverage_audit",
    "load_clustering_prompt",
    "load_prompt",
    "parse_clustering_result",
    "prompt_file_path",
    "render_clustering_user_payload",
]
