from __future__ import annotations

from common.llm_response import LlmResponse
from common.providers import ModelSpec, call_llm_detailed
from common.transcripts import TranscriptCase, build_turn_catalog
from filtering.lib import (
    FilteringResult,
    filtering_output_schema,
    parse_filtering_result,
    render_filtering_user_payload,
)


def run_filtering(
    *,
    case: TranscriptCase,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v001",
) -> tuple[FilteringResult, LlmResponse]:
    catalog = build_turn_catalog(case.transcript_json)
    user_payload = render_filtering_user_payload(
        case=case,
        prompt_version=prompt_version,
    )
    output_schema = filtering_output_schema(
        catalog,
        prompt_version=prompt_version,
    )
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
        output_schema=output_schema,
    )
    result = parse_filtering_result(llm_response.content)
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
    return result, llm_response
