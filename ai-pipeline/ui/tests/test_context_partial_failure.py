from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_pipeline_core.common.context_spans import ClassifyClustersResult, Span, SpanKind, TriageResult
from document_pipeline_core.common.llm_response import LlmResponse
from harness.context_session import ContextLlmCall, ContextPipelinePartialError, ContextPipelineRun
from ui.context_runner import run_context_ad_hoc_pipeline_step
from ui.e2e_pipeline import E2EStepFailed, run_e2e_step
from ui.e2e_viewer import build_e2e_step_states, is_renderable_context_payload, resolve_e2e_pipeline_steps
from ui.runner import PipelineRunOutput, StepConfig


def _step_config() -> StepConfig:
    return StepConfig(
        provider="openai",
        model="gpt",
        prompt_version="v001",
        openai_reasoning_effort=None,
        linked_evidence_two_step=False,
    )


def test_run_context_ad_hoc_pipeline_step_persists_partial_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = [
        Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a"),
        Span(id="s2", doc="doc", kind=SpanKind.LINE, text="b"),
    ]
    partial_run = ContextPipelineRun(
        session_id="adhoc",
        template_id="consulta_estructurada_v001",
        encounter_date=None,
        doctor_items=[],
        is_pasted=False,
        triage_result=TriageResult(),
        directives=[],
        approved_note_spans=[],
        document_spans=spans,
        span_pool=spans,
        filtered_spans=spans,
        clusters=[],
        classify_result=ClassifyClustersResult(),
        adapter_jobs={},
        section_context={},
        section_evidence={},
        llm_calls=[
            ContextLlmCall(
                label="cluster_spans",
                provider="openai",
                model="gpt",
                llm_response=LlmResponse(content="{}", usage={}),
            )
        ],
        stopped_after_step="cluster_spans",
        pipeline_error="context_cluster_missing_span_ids: ['s2']",
    )

    def _raise_partial(**_kwargs: object) -> ContextPipelineRun:
        raise ContextPipelinePartialError(
            "context_cluster_missing_span_ids: ['s2']",
            failed_step="cluster_spans",
            partial_run=partial_run,
            diagnostics={
                "missing_span_ids": ["s2"],
                "missing_spans": [{"id": "s2", "doc": "doc", "kind": "line", "text": "b"}],
                "raw_response": '{"clusters":[]}',
            },
        )

    persisted: dict[str, object] = {}

    def _fake_persist(path: Path, record: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")
        persisted.update(record)

    from contextlib import contextmanager

    @contextmanager
    def _noop_env(_config: object):
        yield

    monkeypatch.setattr("ui.context_runner.run_context_pipeline_ad_hoc", _raise_partial)
    monkeypatch.setattr("ui.runner._persist_results", _fake_persist)
    monkeypatch.setattr("ui.runner.apply_step_config_env", _noop_env)
    monkeypatch.setattr("harness.paths.AI_PIPELINE_ROOT", tmp_path)

    output = run_context_ad_hoc_pipeline_step(
        session_id="adhoc",
        template_id="consulta_estructurada_v001",
        config=_step_config(),
        doctor_note="Nota breve.",
    )

    assert output.result_record["step_status"] == "failed"
    assert output.result_record["pipeline_status"] == "partial"
    assert output.result_record["stopped_after_step"] == "cluster_spans"
    assert output.result_record["missing_span_ids"] == ["s2"]
    assert output.result_record["filtered_spans"]
    assert is_renderable_context_payload(output.result_record)


def test_run_e2e_step_treats_failed_record_as_step_failure() -> None:
    failed_output = PipelineRunOutput(
        step="context_ad_hoc_pipeline",
        result_record={
            "step_status": "failed",
            "error_message": "context_cluster_missing_span_ids: ['s2']",
            "run_mode": "adhoc_context_pipeline",
            "pipeline_status": "partial",
        },
        output_path=Path("/tmp/context.json"),
    )

    with pytest.raises(E2EStepFailed) as exc_info:
        run_e2e_step(
            step="context_ad_hoc_pipeline",
            outputs=[],
            config=_step_config(),
            run_fn=lambda: failed_output,
        )

    assert exc_info.value.failed_output is failed_output
    assert exc_info.value.step == "context_ad_hoc_pipeline"


def test_e2e_step_states_context_partial_failure_before_generation() -> None:
    outputs_by_step = {
        "filtering": {"result_record": {}},
        "clustering": {"result_record": {}},
        "classification": {"result_record": {}},
        "context_ad_hoc_pipeline": {
            "result_record": {
                "step_status": "failed",
                "pipeline_status": "partial",
                "stopped_after_step": "cluster_spans",
            }
        },
    }
    pipeline_steps = resolve_e2e_pipeline_steps(outputs_by_step, include_context=True)
    states = build_e2e_step_states(
        pipeline_steps=pipeline_steps,
        outputs_by_step=outputs_by_step,
        status="failed",
        failed_step="context_ad_hoc_pipeline",
    )
    assert states["context_ad_hoc_pipeline"] == "failed"
    assert states["generation"] == "skipped"
