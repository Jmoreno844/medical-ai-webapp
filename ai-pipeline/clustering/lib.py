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
from common.transcripts import TranscriptCase, build_turn_catalog

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "clustering"
DEFAULT_CASES_INDEX = AI_PIPELINE_ROOT / "cases" / "index.json"

ClusteringCase = TranscriptCase


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


def format_clustering_output_for_detail(
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
        "clustering_result",
        "turn_coverage",
        "repair_passes",
        "error",
    ):
        if key in output:
            compact[key] = output[key]
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
    "enrich_clustering_result_for_export",
    "format_clustering_output_for_detail",
    "format_debug_output",
    "format_turn_coverage_audit",
    "load_prompt",
    "parse_clustering_result",
    "prompt_file_path",
]
