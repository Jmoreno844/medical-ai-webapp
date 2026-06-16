from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.e2e_runs import (
    E2E_RUNS_DIR,
    list_e2e_runs,
    load_e2e_run_outputs,
    save_e2e_run,
)
from ui.runner import PipelineRunOutput


@pytest.fixture
def e2e_runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runs_dir = tmp_path / "e2e_runs"
    monkeypatch.setattr("ui.e2e_runs.E2E_RUNS_DIR", runs_dir)
    return runs_dir


def _write_step_result(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_output(
    *,
    step: str,
    result_dir: Path,
    run_started_at: str,
    extra: dict[str, object] | None = None,
) -> PipelineRunOutput:
    output_path = result_dir / f"{run_started_at.replace(':', '').replace('-', '')[:15]}_{step}.json"
    record: dict[str, object] = {
        "run_started_at": run_started_at,
        "step": step,
    }
    if extra:
        record.update(extra)
    _write_step_result(output_path, record)
    return PipelineRunOutput(
        step=step,
        result_record=record,
        output_path=output_path,
    )


def test_save_and_list_e2e_run(e2e_runs_dir: Path, tmp_path: Path) -> None:
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    outputs = [
        _make_output(step="filtering", result_dir=result_dir, run_started_at=started_at),
        _make_output(step="clustering", result_dir=result_dir, run_started_at=started_at),
        _make_output(
            step="classification",
            result_dir=result_dir,
            run_started_at=started_at,
        ),
        _make_output(step="generation", result_dir=result_dir, run_started_at=started_at),
    ]

    manifest_path = save_e2e_run(
        outputs=outputs,
        case_id="case3",
        session_id="case3",
        template_id="soap_v1",
    )

    assert manifest_path.parent == e2e_runs_dir
    assert manifest_path.name == "20260613T165459_e2e_case3_case3.json"

    runs = list_e2e_runs()
    assert len(runs) == 1
    assert runs[0].case_id == "case3"
    assert runs[0].session_id == "case3"
    assert runs[0].template_id == "soap_v1"
    assert "case3" in runs[0].label


def test_load_e2e_run_outputs_links_clustering(
    e2e_runs_dir: Path,
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    clustering_path = result_dir / "clustering.json"
    classification_path = result_dir / "classification.json"
    generation_path = result_dir / "generation.json"

    _write_step_result(clustering_path, {"run_started_at": started_at})
    _write_step_result(classification_path, {"run_started_at": started_at})
    _write_step_result(generation_path, {"run_started_at": started_at})

    outputs = [
        PipelineRunOutput(
            step="filtering",
            result_record={"run_started_at": started_at},
            output_path=result_dir / "filtering.json",
        ),
        PipelineRunOutput(
            step="clustering",
            result_record={"run_started_at": started_at},
            output_path=clustering_path,
        ),
        PipelineRunOutput(
            step="classification",
            result_record={"run_started_at": started_at},
            output_path=classification_path,
        ),
        PipelineRunOutput(
            step="generation",
            result_record={"run_started_at": started_at},
            output_path=generation_path,
        ),
    ]
    for output in outputs[:1]:
        _write_step_result(output.output_path, output.result_record)

    manifest_path = save_e2e_run(
        outputs=outputs,
        case_id="case1",
        session_id="case1",
        template_id="soap_v1",
        include_context=True,
        context_case_id="case1",
    )

    loaded = load_e2e_run_outputs(manifest_path)
    by_step = {entry["step"]: entry for entry in loaded}

    assert by_step["classification"]["result_record"]["clustering_result_file"] == str(
        clustering_path
    )
    assert by_step["generation"]["result_record"]["clustering_result_file"] == str(
        clustering_path
    )


def test_load_e2e_run_outputs_missing_step_raises(
    e2e_runs_dir: Path,
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    filtering_path = result_dir / "filtering.json"
    _write_step_result(filtering_path, {"run_started_at": started_at})

    outputs = [
        PipelineRunOutput(
            step="filtering",
            result_record={"run_started_at": started_at},
            output_path=filtering_path,
        ),
        PipelineRunOutput(
            step="clustering",
            result_record={"run_started_at": started_at},
            output_path=result_dir / "missing_clustering.json",
        ),
    ]
    manifest_path = save_e2e_run(
        outputs=outputs,
        case_id="case1",
        session_id="case1",
        template_id="soap_v1",
    )

    with pytest.raises(FileNotFoundError, match="missing_clustering"):
        load_e2e_run_outputs(manifest_path)


def test_save_e2e_run_empty_outputs_raises() -> None:
    with pytest.raises(ValueError, match="e2e_run_outputs_empty"):
        save_e2e_run(
            outputs=[],
            case_id="case1",
            session_id="case1",
            template_id="soap_v1",
        )


def test_load_e2e_run_outputs_preserves_generation_audit_fields(
    e2e_runs_dir: Path,
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results"
    started_at = "2026-06-13T16:54:59+00:00"
    generation_path = result_dir / "generation.json"
    generation_record = {
        "run_started_at": started_at,
        "section_outputs": [
            {
                "section_id": "motivo_consulta",
                "generation_route": "two_step",
                "planner_items": [{"text": "Cefalea.", "e": ["t0"]}],
                "planned_items_block": "[1] Cefalea. evidence: t0",
                "llm_responses": [
                    {
                        "step": "planner",
                        "content": '{"items":[{"text":"Cefalea.","e":["t0"]}]}',
                        "usage": {},
                        "request_params": {},
                    },
                    {"step": "renderer", "content": "final", "usage": {}, "request_params": {}},
                ],
                "generation_result": {
                    "section_id": "motivo_consulta",
                    "content": "Cefalea. {{e:t0}}",
                },
            }
        ],
    }
    _write_step_result(generation_path, generation_record)

    outputs = [
        _make_output(step="filtering", result_dir=result_dir, run_started_at=started_at),
        _make_output(step="clustering", result_dir=result_dir, run_started_at=started_at),
        _make_output(step="classification", result_dir=result_dir, run_started_at=started_at),
        PipelineRunOutput(
            step="generation",
            result_record=generation_record,
            output_path=generation_path,
        ),
    ]
    manifest_path = save_e2e_run(
        outputs=outputs,
        case_id="case1",
        session_id="case1",
        template_id="soap_v1",
    )

    loaded = load_e2e_run_outputs(manifest_path)
    generation_entry = next(entry for entry in loaded if entry["step"] == "generation")
    section_output = generation_entry["result_record"]["section_outputs"][0]
    assert section_output["generation_route"] == "two_step"
    assert section_output["planner_items"][0]["e"] == ["t0"]
    assert section_output["llm_responses"][0]["step"] == "planner"
