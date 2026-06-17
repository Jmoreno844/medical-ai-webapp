from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_pipeline_core.generation.lib import GenerationValidationError
from ui.e2e_pipeline import build_generation_failure_record, persist_failed_step_output
from ui.e2e_viewer import extract_generation_failed_display
from ui.runner import PipelineRunOutput, StepConfig


def _write_step_result(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_output(
    *,
    step: str,
    result_dir: Path,
    run_started_at: str,
) -> PipelineRunOutput:
    output_path = result_dir / f"{step}.json"
    record = {"run_started_at": run_started_at, "step": step}
    _write_step_result(output_path, record)
    return PipelineRunOutput(step=step, result_record=record, output_path=output_path)


def _step_config() -> StepConfig:
    return StepConfig(
        provider="openai",
        model="gpt",
        prompt_version="v001",
        openai_reasoning_effort=None,
        linked_evidence_two_step=False,
    )


def test_persist_failed_generation_output_includes_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ui.e2e_pipeline.E2E_FAILED_RESULTS_DIR", tmp_path / "failed")
    filtering = _make_output(
        step="filtering",
        result_dir=tmp_path / "results",
        run_started_at="2026-06-13T16:54:59+00:00",
    )
    exc = GenerationValidationError(
        "ai_pipeline_openai_empty_response",
        section_id="motivo_consulta",
        section_heading="Motivo de consulta",
        generation_route="direct",
        generation_substep="direct",
        cluster_ids=["case1_a"],
        context_present=False,
        context_chars=0,
        prompt_version="v001",
        partial_response="Paciente con dolor torácico...",
        partial_thinking="plan parcial",
        response_output_item_types=["reasoning", "message"],
        response_message_statuses=["incomplete"],
        response_status="incomplete",
        retry_count=1,
    )
    failed = persist_failed_step_output(
        step="generation",
        exc=exc,
        prior_outputs=[filtering],
        config=_step_config(),
        session_id="case1",
    )
    assert failed.result_record["section_id"] == "motivo_consulta"
    assert failed.result_record["generation_substep"] == "direct"
    assert failed.result_record["partial_response"] == "Paciente con dolor torácico..."
    assert failed.result_record["response_status"] == "incomplete"
    assert failed.result_record["retry_count"] == 1


def test_run_e2e_pipeline_partial_on_generation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ui.e2e_pipeline.E2E_FAILED_RESULTS_DIR", tmp_path / "failed")
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    filtering_output = _make_output(
        step="filtering", result_dir=result_dir, run_started_at=started_at
    )
    filtering_output.result_record["filtering_result"] = {"drop_turn_ids": []}
    clustering_output = _make_output(
        step="clustering", result_dir=result_dir, run_started_at=started_at
    )
    classification_output = _make_output(
        step="classification", result_dir=result_dir, run_started_at=started_at
    )
    classification_output.result_record["classification_session_result"] = {
        "assignments": []
    }

    monkeypatch.setattr(
        "ui.discovery.load_transcript_case",
        lambda case_id: type(
            "Case", (), {"id": case_id, "transcript_json": {}, "notes": ""}
        )(),
    )
    monkeypatch.setattr(
        "ui.runner.run_filtering_step",
        lambda **kwargs: filtering_output,
    )
    monkeypatch.setattr(
        "ui.runner.run_clustering_step",
        lambda **kwargs: clustering_output,
    )
    monkeypatch.setattr(
        "ui.runner.clusters_from_clustering_result",
        lambda record, session_id, template_id: [],
    )
    monkeypatch.setattr(
        "ui.runner.run_classification_step",
        lambda **kwargs: classification_output,
    )
    monkeypatch.setattr(
        "ui.runner.assignments_from_classification_record",
        lambda record: [],
    )

    def _raise_generation(**kwargs: object) -> PipelineRunOutput:
        raise GenerationValidationError(
            "ai_pipeline_openai_empty_response",
            section_id="motivo_consulta",
            section_heading="Motivo de consulta",
            generation_route="direct",
            generation_substep="direct",
            cluster_ids=["case1_a"],
            prompt_version="v001",
            retry_count=1,
        )

    monkeypatch.setattr("ui.runner.run_generation_step", _raise_generation)

    from ui.runner import run_e2e_pipeline

    result = run_e2e_pipeline(
        case_id="case1",
        session_id="case1",
        template_id="soap_v1",
        filtering_config=_step_config(),
        clustering_config=_step_config(),
        classification_config=_step_config(),
        generation_config=_step_config(),
    )

    assert result.status == "failed"
    assert result.failed_step == "generation"
    failed_record = result.outputs[-1].result_record
    assert failed_record["section_id"] == "motivo_consulta"
    assert failed_record["generation_substep"] == "direct"
    assert failed_record["retry_count"] == 1


def test_build_generation_failure_record_from_validation_error() -> None:
    exc = GenerationValidationError(
        "ai_pipeline_openai_empty_response",
        section_id="motivo_consulta",
        section_heading="Motivo de consulta",
        generation_route="cluster_planner",
        generation_substep="cluster_renderer",
        cluster_id="case1_cluster_a",
        prompt_version="v001",
        partial_response="Paciente con dolor torácico...",
        response_status="incomplete",
        retry_count=1,
    )
    record = build_generation_failure_record(exc, config=_step_config())
    assert record["section_id"] == "motivo_consulta"
    assert record["generation_substep"] == "cluster_renderer"
    assert record["cluster_id"] == "case1_cluster_a"
    assert record["partial_response"] == "Paciente con dolor torácico..."
    assert record["response_status"] == "incomplete"
    assert record["provider"] == "openai"


def test_extract_generation_failed_display_renderer_planner_output() -> None:
    record = {
        "section_id": "motivo_consulta",
        "generation_substep": "renderer",
        "error_message": "generation_evidence_marker_unknown",
        "planner_items": [{"text": "Cefalea.", "e": ["t0"]}],
        "planned_items_block": "[1] Cefalea. evidence: t0",
        "provider": "openai",
        "model": "gpt",
        "prompt_version": "v001",
    }
    display = extract_generation_failed_display(record)
    assert display["section_id"] == "motivo_consulta"
    assert display["generation_substep"] == "renderer"
    assert display["planner_items"] == [{"text": "Cefalea.", "e": ["t0"]}]


def test_extract_generation_failed_display_openai_partial_response() -> None:
    record = {
        "section_id": "motivo_consulta",
        "generation_substep": "cluster_renderer",
        "error_message": "ai_pipeline_openai_empty_response",
        "partial_response": "Paciente con dolor torácico...",
        "partial_thinking": "plan parcial",
        "response_status": "incomplete",
        "response_output_item_types": ["reasoning", "message"],
        "response_message_statuses": ["incomplete"],
    }
    display = extract_generation_failed_display(record)
    assert display["partial_response"] == "Paciente con dolor torácico..."
    assert display["partial_thinking"] == "plan parcial"
    assert display["response_status"] == "incomplete"
    assert display["response_output_item_types"] == ["reasoning", "message"]
