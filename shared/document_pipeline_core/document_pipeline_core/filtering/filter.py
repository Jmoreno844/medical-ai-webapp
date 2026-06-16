from __future__ import annotations

from document_pipeline_core.common.llm_response import LlmResponse
from document_pipeline_core.common.providers import ModelSpec, call_llm_detailed
from document_pipeline_core.common.transcripts import TranscriptCase, build_turn_catalog
from document_pipeline_core.filtering.lib import (
    FilteringResult,
    filtering_output_schema,
    filtering_uses_py_prompt,
    parse_filtering_result,
    render_filtering_user_payload,
)
from document_pipeline_core.filtering.protection import (
    FilteringRunDiagnostics,
    build_filtering_v002_payload,
    compute_turn_protection,
    sanitize_filtering_drop_turn_ids,
)


def _empty_filtering_llm_response() -> LlmResponse:
    return LlmResponse(
        content='{"drop_turn_ids": []}',
        request_params={
            "filtering_llm_skipped": True,
            "reason": "no_drop_eligible_turns",
        },
    )


def _validate_drop_turn_ids(
    drop_turn_ids: list[int],
    *,
    known_turn_ids: set[int],
) -> None:
    seen: set[int] = set()
    for turn_id in drop_turn_ids:
        if turn_id not in known_turn_ids:
            raise ValueError(f"filtering_unknown_turn_id: {turn_id!r}")
        if turn_id in seen:
            raise ValueError(f"filtering_duplicate_drop_turn_id: {turn_id!r}")
        seen.add(turn_id)


def run_filtering(
    *,
    case: TranscriptCase,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v001",
) -> tuple[FilteringResult, LlmResponse, FilteringRunDiagnostics | None]:
    catalog = build_turn_catalog(case.transcript_json)
    known_turn_ids = {int(item["turn_id"]) for item in catalog}
    diagnostics: FilteringRunDiagnostics | None = None

    if filtering_uses_py_prompt(prompt_version):
        protection = compute_turn_protection(catalog)
        _, payload_mode = build_filtering_v002_payload(catalog, protection)
        user_payload = render_filtering_user_payload(
            case=case,
            prompt_version=prompt_version,
            protection=protection,
        )
        diagnostics = FilteringRunDiagnostics.from_protection(
            protection,
            filtering_payload_mode=payload_mode,
        )

        if not protection.drop_eligible_turn_ids:
            result = FilteringResult(drop_turn_ids=[])
            diagnostics = FilteringRunDiagnostics.from_protection(
                protection,
                filtering_payload_mode=payload_mode,
                llm_skipped=True,
            )
            return result, _empty_filtering_llm_response(), diagnostics

        output_schema = filtering_output_schema(
            catalog,
            prompt_version=prompt_version,
            drop_eligible_turn_ids=protection.drop_eligible_turn_ids,
        )
        llm_response = call_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=system_prompt,
            user=user_payload,
            output_schema=output_schema,
        )
        parsed = parse_filtering_result(llm_response.content)
        sanitized_drop_ids = sanitize_filtering_drop_turn_ids(
            parsed.drop_turn_ids,
            drop_eligible_turn_ids=protection.drop_eligible_turn_ids,
        )
        _validate_drop_turn_ids(sanitized_drop_ids, known_turn_ids=known_turn_ids)
        return FilteringResult(drop_turn_ids=sanitized_drop_ids), llm_response, diagnostics

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
    _validate_drop_turn_ids(result.drop_turn_ids, known_turn_ids=known_turn_ids)
    return result, llm_response, diagnostics
