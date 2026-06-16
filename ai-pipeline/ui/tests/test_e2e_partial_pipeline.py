from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_pipeline_core.classification.lib import ClassificationValidationError
from ui.e2e_pipeline import persist_failed_step_output, prior_output_paths
from ui.e2e_runs import load_e2e_run, save_e2e_run
from ui.e2e_viewer import build_e2e_step_states, generation_succeeded
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


def test_prior_output_paths_maps_steps() -> None:
    outputs = [
        PipelineRunOutput(step="filtering", result_record={}, output_path=Path("/a.json")),
        PipelineRunOutput(step="clustering", result_record={}, output_path=Path("/b.json")),
    ]
    assert prior_output_paths(outputs) == {
        "filtering": "/a.json",
        "clustering": "/b.json",
    }


def test_persist_failed_step_output_includes_classification_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ui.e2e_pipeline.E2E_FAILED_RESULTS_DIR", tmp_path)
    prior = [
        _make_output(
            step="filtering",
            result_dir=tmp_path,
            run_started_at="2026-06-13T16:54:59+00:00",
        )
    ]
    exc = ClassificationValidationError(
        "classification_invalid_section_ids: cluster_id='c1' unknown_section_ids=['bad']",
        raw_response='{"assignments":[]}',
        classification_result={"assignments": []},
        batch_assignment_audit={"invalid_section_cluster_ids": ["c1"]},
        cluster_ids=["c1"],
    )
    failed = persist_failed_step_output(
        step="classification",
        exc=exc,
        prior_outputs=prior,
        session_id="case1",
    )
    assert failed.result_record["step_status"] == "failed"
    assert failed.result_record["raw_response"] == '{"assignments":[]}'
    assert failed.result_record["prior_output_paths"]["filtering"] == str(
        prior[0].output_path
    )
    assert failed.output_path.is_file()


def test_run_e2e_pipeline_partial_on_classification_failure(
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

    monkeypatch.setattr(
        "ui.discovery.load_transcript_case",
        lambda case_id: type("Case", (), {"id": case_id, "transcript_json": {}, "notes": ""})(),
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

    def _raise_classification(**kwargs: object) -> PipelineRunOutput:
        raise ClassificationValidationError(
            "classification_invalid_section_ids: cluster_id='c1' unknown_section_ids=['bad']",
            raw_response="{}",
            classification_result={"assignments": []},
            batch_assignment_audit={"invalid_section_cluster_ids": ["c1"]},
            cluster_ids=["c1"],
        )

    monkeypatch.setattr("ui.runner.run_classification_step", _raise_classification)
    generation_called = {"value": False}

    def _generation_should_not_run(**kwargs: object) -> PipelineRunOutput:
        generation_called["value"] = True
        raise AssertionError("generation should not run")

    monkeypatch.setattr("ui.runner.run_generation_step", _generation_should_not_run)

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
    assert result.failed_step == "classification"
    assert [output.step for output in result.outputs] == [
        "filtering",
        "clustering",
        "classification",
    ]
    assert result.outputs[-1].result_record["step_status"] == "failed"
    assert generation_called["value"] is False


@pytest.fixture
def e2e_runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runs_dir = tmp_path / "e2e_runs"
    monkeypatch.setattr("ui.e2e_runs.E2E_RUNS_DIR", runs_dir)
    return runs_dir


def test_save_and_load_failed_e2e_manifest(
    e2e_runs_dir: Path,
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    filtering = _make_output(step="filtering", result_dir=result_dir, run_started_at=started_at)
    clustering = _make_output(step="clustering", result_dir=result_dir, run_started_at=started_at)
    failed_path = result_dir / "classification_failed.json"
    failed_record = {
        "step_status": "failed",
        "step": "classification",
        "run_started_at": started_at,
        "error_message": "classification_invalid_section_ids",
    }
    _write_step_result(failed_path, failed_record)
    failed_output = PipelineRunOutput(
        step="classification",
        result_record=failed_record,
        output_path=failed_path,
    )

    manifest_path = save_e2e_run(
        outputs=[filtering, clustering, failed_output],
        case_id="case1",
        session_id="case1",
        template_id="soap_v1",
        status="failed",
        failed_step="classification",
        error_message="classification_invalid_section_ids",
    )

    loaded = load_e2e_run(manifest_path)
    assert loaded.status == "failed"
    assert loaded.failed_step == "classification"
    assert [entry["step"] for entry in loaded.outputs] == [
        "filtering",
        "clustering",
        "classification",
    ]


def test_build_e2e_step_states_marks_skipped_after_failure() -> None:
    outputs_by_step = {
        "filtering": {"result_record": {"step_status": "ok"}},
        "clustering": {"result_record": {"step_status": "ok"}},
        "classification": {
            "result_record": {
                "step_status": "failed",
                "error_message": "boom",
            }
        },
    }
    states = build_e2e_step_states(
        pipeline_steps=("filtering", "clustering", "classification", "generation"),
        outputs_by_step=outputs_by_step,
        status="failed",
        failed_step="classification",
    )
    assert states["filtering"] == "success"
    assert states["classification"] == "failed"
    assert states["generation"] == "skipped"
    assert generation_succeeded(states) is False
