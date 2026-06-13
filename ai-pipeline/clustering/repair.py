from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from common.json_utils import extract_json_object
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path
from common.providers import ModelSpec, call_llm
from clustering.lib import (
    PROMPTS_DIR,
    ClusteringResult,
    TopicCluster,
    TurnCoverageAudit,
    audit_turn_coverage,
)

REPAIR_PROMPT_FILENAME_STEM = "clustering_repair"
DEFAULT_REPAIR_PROMPT_VERSION = "v001"
DEFAULT_MAX_REPAIR_PASSES = 2
DEFAULT_REPAIR_CONTEXT_WINDOW = 2


class ClusteringRepairAssignment(BaseModel):
    turn_id: int
    topic_label: str


class ClusteringRepairResult(BaseModel):
    assignments: list[ClusteringRepairAssignment] = Field(default_factory=list)
    unassigned_turn_ids: list[int] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ClusteringRepairPassRecord:
    pass_index: int
    missing_turn_ids_before: list[int]
    assignments: list[dict[str, object]]
    unassigned_turn_ids: list[int]
    still_missing_after: list[int]
    response_time_ms: int
    raw_response: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pass_index": self.pass_index,
            "missing_turn_ids_before": self.missing_turn_ids_before,
            "assignments": self.assignments,
            "unassigned_turn_ids": self.unassigned_turn_ids,
            "still_missing_after": self.still_missing_after,
            "response_time_ms": self.response_time_ms,
        }


class IncompleteTurnCoverageError(ValueError):
    def __init__(self, *, missing_turn_ids: list[int], repair_pass_count: int) -> None:
        self.missing_turn_ids = list(missing_turn_ids)
        self.repair_pass_count = repair_pass_count
        super().__init__(
            "clustering_incomplete_turn_coverage: "
            f"missing_turn_ids={missing_turn_ids} "
            f"after {repair_pass_count} repair pass(es)"
        )


def clustering_repair_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=REPAIR_PROMPT_FILENAME_STEM,
        version=version,
    )


def load_clustering_repair_prompt(version: str = DEFAULT_REPAIR_PROMPT_VERSION) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=REPAIR_PROMPT_FILENAME_STEM,
        version=version,
    )


def parse_clustering_repair_result(raw: str) -> ClusteringRepairResult:
    payload = extract_json_object(raw)
    try:
        return ClusteringRepairResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"clustering_repair_invalid_result: {exc}") from exc


def _catalog_by_id(
    catalog: list[dict[str, object]],
) -> dict[int, dict[str, object]]:
    return {int(item["turn_id"]): item for item in catalog}


def _turn_payload_item(turn: dict[str, object]) -> dict[str, object]:
    return {
        "turn_id": turn["turn_id"],
        "speaker": turn["speaker"],
        "text": turn["text"],
    }


def _context_turns_for_missing(
    *,
    turn_id: int,
    catalog_by_id: dict[int, dict[str, object]],
    context_window: int,
) -> list[dict[str, object]]:
    if context_window <= 0:
        return []
    context_turns: list[dict[str, object]] = []
    for neighbor_id in range(turn_id - context_window, turn_id + context_window + 1):
        if neighbor_id == turn_id:
            continue
        neighbor = catalog_by_id.get(neighbor_id)
        if neighbor is None:
            continue
        context_turns.append(_turn_payload_item(neighbor))
    return context_turns


def build_repair_user_payload(
    *,
    result: ClusteringResult,
    catalog: list[dict[str, object]],
    missing_turn_ids: list[int],
    context_window: int = DEFAULT_REPAIR_CONTEXT_WINDOW,
) -> str:
    catalog_by_id = _catalog_by_id(catalog)
    existing_clusters: list[dict[str, object]] = []
    for cluster in result.clusters:
        sample_turns: list[dict[str, object]] = []
        if cluster.turn_ids:
            first_turn = catalog_by_id.get(cluster.turn_ids[0])
            if first_turn is not None:
                sample_turns.append(_turn_payload_item(first_turn))
            if len(cluster.turn_ids) > 1:
                last_turn = catalog_by_id.get(cluster.turn_ids[-1])
                if last_turn is not None:
                    sample_turns.append(_turn_payload_item(last_turn))
        existing_clusters.append(
            {
                "topic_label": cluster.topic_label,
                "turn_ids": list(cluster.turn_ids),
                "sample_turns": sample_turns,
            }
        )

    missing_turns: list[dict[str, object]] = []
    for turn_id in missing_turn_ids:
        turn = catalog_by_id.get(turn_id)
        if turn is None:
            continue
        missing_turns.append(
            {
                **_turn_payload_item(turn),
                "context_turns": _context_turns_for_missing(
                    turn_id=turn_id,
                    catalog_by_id=catalog_by_id,
                    context_window=context_window,
                ),
            }
        )

    payload = {
        "existing_clusters": existing_clusters,
        "missing_turns": missing_turns,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def apply_repair_assignments(
    result: ClusteringResult,
    repair: ClusteringRepairResult,
    *,
    missing_turn_ids: list[int],
) -> ClusteringResult:
    missing_set = set(missing_turn_ids)
    clusters_by_label = {
        cluster.topic_label: TopicCluster(
            topic_label=cluster.topic_label,
            turn_ids=list(cluster.turn_ids),
        )
        for cluster in result.clusters
    }
    assigned_missing: set[int] = set()
    unassigned_turn_ids = list(result.unassigned_turn_ids)

    for assignment in repair.assignments:
        if assignment.turn_id not in missing_set:
            raise ValueError(
                f"clustering_repair_unknown_missing_turn_id: {assignment.turn_id!r}"
            )
        if assignment.turn_id in assigned_missing:
            raise ValueError(
                f"clustering_repair_duplicate_turn_id: {assignment.turn_id!r}"
            )
        cluster = clusters_by_label.get(assignment.topic_label.strip())
        if cluster is None:
            raise ValueError(
                f"clustering_repair_unknown_topic_label: {assignment.topic_label!r}"
            )
        cluster.turn_ids.append(assignment.turn_id)
        assigned_missing.add(assignment.turn_id)

    for turn_id in repair.unassigned_turn_ids:
        if turn_id not in missing_set:
            raise ValueError(
                f"clustering_repair_unknown_unassigned_turn_id: {turn_id!r}"
            )
        if turn_id in assigned_missing:
            raise ValueError(
                f"clustering_repair_duplicate_unassigned_turn_id: {turn_id!r}"
            )
        unassigned_turn_ids.append(turn_id)
        assigned_missing.add(turn_id)

    repaired_clusters = list(clusters_by_label.values())
    for cluster in repaired_clusters:
        cluster.turn_ids.sort()

    return ClusteringResult(
        clusters=repaired_clusters,
        unassigned_turn_ids=sorted(set(unassigned_turn_ids)),
    )


def run_clustering_repair(
    *,
    result: ClusteringResult,
    catalog: list[dict[str, object]],
    missing_turn_ids: list[int],
    model_spec: ModelSpec,
    system_prompt: str,
    context_window: int = DEFAULT_REPAIR_CONTEXT_WINDOW,
) -> tuple[ClusteringRepairResult, str, int]:
    if not missing_turn_ids:
        raise ValueError("clustering_repair_requires_missing_turn_ids")
    user_payload = build_repair_user_payload(
        result=result,
        catalog=catalog,
        missing_turn_ids=missing_turn_ids,
        context_window=context_window,
    )
    started_at = time.perf_counter()
    raw_response = call_llm(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    repair_result = parse_clustering_repair_result(raw_response)
    return repair_result, raw_response, response_time_ms


def repair_clustering_coverage(
    *,
    result: ClusteringResult,
    catalog: list[dict[str, object]],
    model_spec: ModelSpec,
    repair_system_prompt: str,
    max_repair_passes: int = DEFAULT_MAX_REPAIR_PASSES,
    context_window: int = DEFAULT_REPAIR_CONTEXT_WINDOW,
) -> tuple[ClusteringResult, list[ClusteringRepairPassRecord]]:
    repaired_result = result
    repair_passes: list[ClusteringRepairPassRecord] = []

    for pass_index in range(max_repair_passes):
        audit = audit_turn_coverage(repaired_result, catalog)
        if audit.is_complete or not audit.missing_turn_ids:
            break

        missing_before = list(audit.missing_turn_ids)
        repair_result, raw_response, response_time_ms = run_clustering_repair(
            result=repaired_result,
            catalog=catalog,
            missing_turn_ids=missing_before,
            model_spec=model_spec,
            system_prompt=repair_system_prompt,
            context_window=context_window,
        )
        repaired_result = apply_repair_assignments(
            repaired_result,
            repair_result,
            missing_turn_ids=missing_before,
        )
        after_audit = audit_turn_coverage(repaired_result, catalog)
        repair_passes.append(
            ClusteringRepairPassRecord(
                pass_index=pass_index + 1,
                missing_turn_ids_before=missing_before,
                assignments=[
                    {
                        "turn_id": item.turn_id,
                        "topic_label": item.topic_label,
                    }
                    for item in repair_result.assignments
                ],
                unassigned_turn_ids=list(repair_result.unassigned_turn_ids),
                still_missing_after=list(after_audit.missing_turn_ids),
                response_time_ms=response_time_ms,
                raw_response=raw_response,
            )
        )

    return repaired_result, repair_passes


def ensure_complete_turn_coverage(
    *,
    result: ClusteringResult,
    catalog: list[dict[str, object]],
    repair_passes: list[ClusteringRepairPassRecord],
) -> TurnCoverageAudit:
    audit = audit_turn_coverage(result, catalog)
    if audit.is_complete:
        return audit
    raise IncompleteTurnCoverageError(
        missing_turn_ids=audit.missing_turn_ids,
        repair_pass_count=len(repair_passes),
    )


__all__ = [
    "DEFAULT_MAX_REPAIR_PASSES",
    "DEFAULT_REPAIR_CONTEXT_WINDOW",
    "DEFAULT_REPAIR_PROMPT_VERSION",
    "ClusteringRepairPassRecord",
    "ClusteringRepairResult",
    "IncompleteTurnCoverageError",
    "apply_repair_assignments",
    "build_repair_user_payload",
    "clustering_repair_prompt_file_path",
    "ensure_complete_turn_coverage",
    "load_clustering_repair_prompt",
    "parse_clustering_repair_result",
    "repair_clustering_coverage",
    "run_clustering_repair",
]
