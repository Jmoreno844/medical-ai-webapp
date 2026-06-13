from __future__ import annotations

from common.providers import ModelSpec, call_llm
from common.transcripts import TranscriptCase, build_turn_catalog, render_user_payload
from filtering.lib import FilteringResult, parse_filtering_result


def run_filtering(
    *,
    case: TranscriptCase,
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[FilteringResult, str]:
    user_payload = render_user_payload(case)
    raw_response = call_llm(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    result = parse_filtering_result(raw_response)
    catalog = build_turn_catalog(case.transcript_json)
    known_turn_ids = {int(item["turn_id"]) for item in catalog}
    seen: set[int] = set()
    for turn_id in result.drop_turn_ids:
        if turn_id not in known_turn_ids:
            raise ValueError(
                f"filtering_unknown_turn_id: {turn_id!r}"
            )
        if turn_id in seen:
            raise ValueError(
                f"filtering_duplicate_drop_turn_id: {turn_id!r}"
            )
        seen.add(turn_id)
    return result, raw_response
