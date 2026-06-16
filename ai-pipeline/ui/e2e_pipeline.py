from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from document_pipeline_core.classification.lib import ClassificationValidationError
from document_pipeline_core.generation.lib import GenerationValidationError
from harness.paths import E2E_FAILED_RESULTS_DIR
from ui.runner import PipelineRunOutput, StepConfig

E2E_FULL_TEMPLATE_ID = "consulta_estructurada_v001"

E2E_STEP_ORDER: tuple[str, ...] = (
    "filtering",
    "clustering",
    "classification",
    "context_ad_hoc_pipeline",
    "context_pipeline",
    "generation",
)


@dataclass(frozen=True, slots=True)
class E2EPipelineResult:
    status: Literal["complete", "failed"]
    outputs: list[PipelineRunOutput]
    failed_step: str | None = None
    error_message: str | None = None
    manifest_path: Path | None = None


class E2EStepFailed(Exception):
    def __init__(
        self,
        *,
        step: str,
        message: str,
        failed_output: PipelineRunOutput,
    ) -> None:
        super().__init__(message)
        self.step = step
        self.message = message
        self.failed_output = failed_output


def prior_output_paths(outputs: list[PipelineRunOutput]) -> dict[str, str]:
    return {output.step: str(output.output_path) for output in outputs}


def _exception_diagnostics(exc: BaseException) -> dict[str, object]:
    diagnostics_fn = getattr(exc, "diagnostics", None)
    if callable(diagnostics_fn):
        payload = diagnostics_fn()
        if isinstance(payload, dict):
            return payload
    if isinstance(exc, ClassificationValidationError):
        return exc.diagnostics()
    if isinstance(exc, GenerationValidationError):
        return exc.diagnostics()
    return {}


def persist_failed_step_output(
    *,
    step: str,
    exc: BaseException,
    prior_outputs: list[PipelineRunOutput],
    config: StepConfig | None = None,
    session_id: str | None = None,
    case_id: str | None = None,
) -> PipelineRunOutput:
    run_started_at = datetime.now(UTC)
    run_finished_at = datetime.now(UTC)
    identifier = session_id or case_id or "e2e"
    output_path = (
        E2E_FAILED_RESULTS_DIR
        / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_failed_{step}_{identifier}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_record: dict[str, object] = {
        "step_status": "failed",
        "step": step,
        "run_mode": "e2e_failed_step",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": run_finished_at.isoformat(),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "prior_output_paths": prior_output_paths(prior_outputs),
        "output_path": str(output_path),
    }
    if session_id:
        result_record["session_id"] = session_id
    if case_id:
        result_record["case_id"] = case_id
    if config is not None:
        result_record["provider"] = config.provider
        result_record["model"] = config.model
        result_record["prompt_version"] = config.prompt_version
        if config.openai_reasoning_effort is not None:
            result_record["openai_reasoning_effort"] = config.openai_reasoning_effort
        if config.linked_evidence_two_step:
            result_record["linked_evidence_two_step"] = True

    result_record.update(_exception_diagnostics(exc))

    output_path.write_text(
        json.dumps(result_record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return PipelineRunOutput(
        step=step,
        result_record=result_record,
        output_path=output_path,
    )


def run_e2e_step(
    *,
    step: str,
    outputs: list[PipelineRunOutput],
    config: StepConfig | None,
    run_fn: Callable[[], PipelineRunOutput],
    session_id: str | None = None,
    case_id: str | None = None,
) -> PipelineRunOutput:
    try:
        output = run_fn()
        if output.result_record.get("step_status") == "failed":
            raise E2EStepFailed(
                step=step,
                message=str(
                    output.result_record.get("error_message", "Step failed")
                ),
                failed_output=output,
            )
        return output
    except E2EStepFailed:
        raise
    except Exception as exc:
        failed_output = persist_failed_step_output(
            step=step,
            exc=exc,
            prior_outputs=outputs,
            config=config,
            session_id=session_id,
            case_id=case_id,
        )
        raise E2EStepFailed(
            step=step,
            message=str(exc),
            failed_output=failed_output,
        ) from exc


__all__ = [
    "E2E_FAILED_RESULTS_DIR",
    "E2E_FULL_TEMPLATE_ID",
    "E2E_STEP_ORDER",
    "E2EPipelineResult",
    "E2EStepFailed",
    "persist_failed_step_output",
    "prior_output_paths",
    "run_e2e_step",
]
