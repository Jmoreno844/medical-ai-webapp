from __future__ import annotations

import time
from dataclasses import dataclass

from common.providers import ModelSpec, call_llm
from common.transcripts import TranscriptCase, build_turn_catalog, render_user_payload
from clustering.lib import ClusteringResult, parse_clustering_result
from clustering.repair import (
    ClusteringRepairPassRecord,
    DEFAULT_MAX_REPAIR_PASSES,
    DEFAULT_REPAIR_CONTEXT_WINDOW,
    DEFAULT_REPAIR_PROMPT_VERSION,
    ensure_complete_turn_coverage,
    load_clustering_repair_prompt,
    repair_clustering_coverage,
)


def run_clustering(
    *,
    case: TranscriptCase,
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[ClusteringResult, str]:
    user_payload = render_user_payload(case)
    raw_response = call_llm(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_clustering_result(raw_response)
    catalog = build_turn_catalog(case.transcript_json)
    known_turn_ids = {item["turn_id"] for item in catalog}
    for cluster in result.clusters:
        for turn_id in cluster.turn_ids:
            if turn_id not in known_turn_ids:
                raise ValueError(
                    f"clustering_unknown_turn_id: {turn_id!r}"
                )
    for turn_id in result.unassigned_turn_ids:
        if turn_id not in known_turn_ids:
            raise ValueError(
                f"clustering_unknown_turn_id: {turn_id!r}"
            )
    return result, raw_response


@dataclass(frozen=True, slots=True)
class ClusteringSessionRun:
    result: ClusteringResult
    raw_response: str
    repair_passes: list[ClusteringRepairPassRecord]
    response_time_ms: int
    repair_response_time_ms: int


def run_clustering_with_repair(
    *,
    case: TranscriptCase,
    model_spec: ModelSpec,
    system_prompt: str,
    repair_system_prompt: str | None = None,
    max_repair_passes: int = DEFAULT_MAX_REPAIR_PASSES,
    context_window: int = DEFAULT_REPAIR_CONTEXT_WINDOW,
    require_complete_coverage: bool = False,
) -> ClusteringSessionRun:
    catalog = build_turn_catalog(case.transcript_json)
    started_at = time.perf_counter()
    result, raw_response = run_clustering(
        case=case,
        model_spec=model_spec,
        system_prompt=system_prompt,
    )
    initial_response_time_ms = int((time.perf_counter() - started_at) * 1000)

    resolved_repair_prompt = (
        repair_system_prompt
        or load_clustering_repair_prompt(DEFAULT_REPAIR_PROMPT_VERSION)
    )
    repaired_result, repair_passes = repair_clustering_coverage(
        result=result,
        catalog=catalog,
        model_spec=model_spec,
        repair_system_prompt=resolved_repair_prompt,
        max_repair_passes=max_repair_passes,
        context_window=context_window,
    )
    repair_response_time_ms = sum(
        repair_pass.response_time_ms for repair_pass in repair_passes
    )

    if require_complete_coverage:
        ensure_complete_turn_coverage(
            result=repaired_result,
            catalog=catalog,
            repair_passes=repair_passes,
        )

    return ClusteringSessionRun(
        result=repaired_result,
        raw_response=raw_response,
        repair_passes=repair_passes,
        response_time_ms=initial_response_time_ms,
        repair_response_time_ms=repair_response_time_ms,
    )
