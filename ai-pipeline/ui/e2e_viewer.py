from __future__ import annotations

E2E_CONTEXT_STEP_KEYS: tuple[str, ...] = (
    "context_ad_hoc_pipeline",
    "context_pipeline",
)

E2E_TRANSCRIPT_STEPS: tuple[str, ...] = (
    "filtering",
    "clustering",
    "classification",
    "generation",
)

StepViewState = str  # success | failed | skipped | not_executed


def context_step_from_outputs(
    outputs_by_step: dict[str, dict[str, object]],
) -> str | None:
    for step in E2E_CONTEXT_STEP_KEYS:
        if step in outputs_by_step:
            return step
    return None


def resolve_e2e_pipeline_steps(
    outputs_by_step: dict[str, dict[str, object]],
    *,
    include_context: bool = False,
) -> tuple[str, ...]:
    steps: list[str] = ["filtering", "clustering", "classification"]
    context_step = context_step_from_outputs(outputs_by_step)
    if context_step is None and include_context:
        context_step = "context_ad_hoc_pipeline"
    if context_step is not None:
        steps.append(context_step)
    steps.append("generation")
    return tuple(steps)


def _step_index(step: str, pipeline_steps: tuple[str, ...]) -> int:
    try:
        return pipeline_steps.index(step)
    except ValueError:
        return len(pipeline_steps)


def build_e2e_step_states(
    *,
    pipeline_steps: tuple[str, ...],
    outputs_by_step: dict[str, dict[str, object]],
    status: str,
    failed_step: str | None,
) -> dict[str, StepViewState]:
    states: dict[str, StepViewState] = {}
    failed_index = (
        _step_index(failed_step, pipeline_steps)
        if status == "failed" and failed_step
        else -1
    )

    for index, step in enumerate(pipeline_steps):
        entry = outputs_by_step.get(step)
        if entry is not None:
            result_record = entry.get("result_record")
            if (
                isinstance(result_record, dict)
                and result_record.get("step_status") == "failed"
            ):
                states[step] = "failed"
            else:
                states[step] = "success"
            continue

        if status == "failed" and failed_index >= 0 and index > failed_index:
            states[step] = "skipped"
        else:
            states[step] = "not_executed"

    return states


def generation_succeeded(step_states: dict[str, StepViewState]) -> bool:
    return step_states.get("generation") == "success"


def extract_generation_failed_display(
    result_record: dict[str, object],
) -> dict[str, object]:
    display: dict[str, object] = {}
    for key in (
        "section_id",
        "section_heading",
        "generation_substep",
        "generation_route",
        "provider",
        "model",
        "prompt_version",
        "error_message",
        "retry_count",
    ):
        value = result_record.get(key)
        if value is not None and value != "":
            display[key] = value

    substep = result_record.get("generation_substep")
    if substep == "renderer":
        for key in ("planner_items", "planned_items_block", "planner_response"):
            value = result_record.get(key)
            if value is not None:
                display[key] = value
    return display


def is_renderable_context_payload(result_record: dict[str, object]) -> bool:
    if result_record.get("pipeline_status") == "partial":
        return True
    run_mode = result_record.get("run_mode")
    if run_mode in {"adhoc_context_pipeline", "context_pipeline_session"}:
        return True
    return any(
        key in result_record
        for key in (
            "triage_result",
            "span_pool",
            "filtered_spans",
            "cluster_spans_result",
        )
    )


__all__ = [
    "E2E_CONTEXT_STEP_KEYS",
    "E2E_TRANSCRIPT_STEPS",
    "build_e2e_step_states",
    "context_step_from_outputs",
    "extract_generation_failed_display",
    "generation_succeeded",
    "is_renderable_context_payload",
    "resolve_e2e_pipeline_steps",
]
