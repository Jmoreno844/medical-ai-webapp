from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.e2e_pipeline import E2E_FULL_TEMPLATE_ID
from ui.e2e_runs import load_e2e_run, save_e2e_run
from ui.e2e_viewer import (
    build_e2e_step_states,
    resolve_e2e_pipeline_steps,
)
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


def _base_e2e_mocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PipelineRunOutput, PipelineRunOutput, PipelineRunOutput]:
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
    return filtering_output, clustering_output, classification_output


def test_run_e2e_pipeline_without_context_skips_ad_hoc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_e2e_mocks(tmp_path, monkeypatch)
    ad_hoc_called = {"value": False}
    generation_claim_file: dict[str, str | None] = {"path": None}

    def _fake_ad_hoc(**kwargs: object) -> PipelineRunOutput:
        ad_hoc_called["value"] = True
        raise AssertionError("ad hoc should not run")

    def _fake_generation(**kwargs: object) -> PipelineRunOutput:
        generation_claim_file["path"] = kwargs.get("claim_classification_result_file")  # type: ignore[assignment]
        return _make_output(
            step="generation",
            result_dir=tmp_path / "results",
            run_started_at="2026-06-13T16:54:59+00:00",
        )

    monkeypatch.setattr("ui.runner.run_context_ad_hoc_pipeline_step", _fake_ad_hoc)
    monkeypatch.setattr("ui.runner.run_generation_step", _fake_generation)

    from ui.runner import run_e2e_pipeline

    result = run_e2e_pipeline(
        case_id="case1",
        session_id="case1",
        template_id=E2E_FULL_TEMPLATE_ID,
        filtering_config=_step_config(),
        clustering_config=_step_config(),
        classification_config=_step_config(),
        generation_config=_step_config(),
    )

    assert result.status == "complete"
    assert ad_hoc_called["value"] is False
    assert generation_claim_file["path"] is None
    assert [output.step for output in result.outputs] == [
        "filtering",
        "clustering",
        "classification",
        "generation",
    ]


def test_run_e2e_pipeline_with_custom_context_calls_ad_hoc_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_e2e_mocks(tmp_path, monkeypatch)
    captured: dict[str, object] = {}
    generation_claim_file: dict[str, str | None] = {"path": None}

    def _fake_ad_hoc(**kwargs: object) -> PipelineRunOutput:
        captured.update(kwargs)
        output_path = tmp_path / "results" / "context_ad_hoc.json"
        record = {
            "run_started_at": "2026-06-13T16:54:59+00:00",
            "section_context": {"motivo_consulta": "brief"},
        }
        _write_step_result(output_path, record)
        return PipelineRunOutput(
            step="context_ad_hoc_pipeline",
            result_record=record,
            output_path=output_path,
        )

    def _fake_generation(**kwargs: object) -> PipelineRunOutput:
        generation_claim_file["path"] = kwargs.get("claim_classification_result_file")  # type: ignore[assignment]
        return _make_output(
            step="generation",
            result_dir=tmp_path / "results",
            run_started_at="2026-06-13T16:54:59+00:00",
        )

    monkeypatch.setattr("ui.runner.run_context_ad_hoc_pipeline_step", _fake_ad_hoc)
    monkeypatch.setattr("ui.runner.run_generation_step", _fake_generation)

    from ui.runner import run_e2e_pipeline

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    result = run_e2e_pipeline(
        case_id="case1",
        session_id="case1",
        template_id=E2E_FULL_TEMPLATE_ID,
        filtering_config=_step_config(),
        clustering_config=_step_config(),
        classification_config=_step_config(),
        generation_config=_step_config(),
        context_config=_step_config(),
        context_doctor_note="Paciente alérgico a penicilina.",
        context_document_pdf_path=pdf_path,
        context_document_id="epicrisis",
    )

    assert result.status == "complete"
    assert captured["template_id"] == E2E_FULL_TEMPLATE_ID
    assert captured["doctor_note"] == "Paciente alérgico a penicilina."
    assert captured["document_pdf_path"] == pdf_path
    assert captured["document_id"] == "epicrisis"
    assert [output.step for output in result.outputs] == [
        "filtering",
        "clustering",
        "classification",
        "context_ad_hoc_pipeline",
        "generation",
    ]
    assert generation_claim_file["path"] == str(
        result.outputs[-2].output_path
    )


def test_run_e2e_pipeline_uses_fixed_template_for_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_e2e_mocks(tmp_path, monkeypatch)
    classification_template: dict[str, str] = {}

    def _capture_classification(**kwargs: object) -> PipelineRunOutput:
        classification_template["template_id"] = str(kwargs.get("template_id"))
        return _make_output(
            step="classification",
            result_dir=tmp_path / "results",
            run_started_at="2026-06-13T16:54:59+00:00",
        )

    monkeypatch.setattr("ui.runner.run_classification_step", _capture_classification)
    monkeypatch.setattr(
        "ui.runner.run_generation_step",
        lambda **kwargs: _make_output(
            step="generation",
            result_dir=tmp_path / "results",
            run_started_at="2026-06-13T16:54:59+00:00",
        ),
    )

    from ui.runner import run_e2e_pipeline

    run_e2e_pipeline(
        case_id="case1",
        session_id="case1",
        template_id=E2E_FULL_TEMPLATE_ID,
        filtering_config=_step_config(),
        clustering_config=_step_config(),
        classification_config=_step_config(),
        generation_config=_step_config(),
    )

    assert classification_template["template_id"] == "consulta_estructurada_v001"


def test_resolve_e2e_pipeline_steps_includes_context_when_present() -> None:
    outputs_by_step = {
        "filtering": {},
        "clustering": {},
        "classification": {},
        "context_ad_hoc_pipeline": {},
        "generation": {},
    }
    steps = resolve_e2e_pipeline_steps(outputs_by_step, include_context=True)
    assert steps == (
        "filtering",
        "clustering",
        "classification",
        "context_ad_hoc_pipeline",
        "generation",
    )


def test_build_e2e_step_states_context_success_before_generation() -> None:
    outputs_by_step = {
        "filtering": {"result_record": {}},
        "clustering": {"result_record": {}},
        "classification": {"result_record": {}},
        "context_ad_hoc_pipeline": {"result_record": {}},
        "generation": {"result_record": {}},
    }
    pipeline_steps = resolve_e2e_pipeline_steps(outputs_by_step, include_context=True)
    states = build_e2e_step_states(
        pipeline_steps=pipeline_steps,
        outputs_by_step=outputs_by_step,
        status="complete",
        failed_step=None,
    )
    assert states["context_ad_hoc_pipeline"] == "success"
    assert states["generation"] == "success"


@pytest.fixture
def e2e_runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runs_dir = tmp_path / "e2e_runs"
    monkeypatch.setattr("ui.e2e_runs.E2E_RUNS_DIR", runs_dir)
    return runs_dir


def test_save_e2e_run_with_custom_context_manifest(
    e2e_runs_dir: Path,
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    outputs = [
        _make_output(step="filtering", result_dir=result_dir, run_started_at=started_at),
        _make_output(step="clustering", result_dir=result_dir, run_started_at=started_at),
        _make_output(step="classification", result_dir=result_dir, run_started_at=started_at),
        _make_output(
            step="context_ad_hoc_pipeline",
            result_dir=result_dir,
            run_started_at=started_at,
        ),
        _make_output(step="generation", result_dir=result_dir, run_started_at=started_at),
    ]

    manifest_path = save_e2e_run(
        outputs=outputs,
        case_id="case1",
        session_id="case1",
        template_id=E2E_FULL_TEMPLATE_ID,
        include_context=True,
    )

    loaded = load_e2e_run(manifest_path)
    assert loaded.outputs[-2]["step"] == "context_ad_hoc_pipeline"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["include_context"] is True
    assert manifest["template_id"] == E2E_FULL_TEMPLATE_ID
