from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ui.discovery import AI_PIPELINE_ROOT, load_result_json
from ui.runner import PipelineRunOutput

E2E_RUNS_DIR = AI_PIPELINE_ROOT / "e2e_runs"
MANIFEST_VERSION = 1
E2ERunStatus = Literal["complete", "failed"]


@dataclass(frozen=True, slots=True)
class E2ERunMeta:
    path: Path
    run_id: str
    label: str
    case_id: str
    session_id: str
    template_id: str
    run_started_at: str
    include_context: bool
    status: E2ERunStatus = "complete"
    failed_step: str | None = None


@dataclass(frozen=True, slots=True)
class LoadedE2ERun:
    manifest_path: Path
    status: E2ERunStatus
    failed_step: str | None
    error_message: str | None
    outputs: list[dict[str, object]]


def _run_label(
    *,
    run_started_at: str,
    case_id: str,
    session_id: str,
    template_id: str,
    include_context: bool,
    status: E2ERunStatus,
    failed_step: str | None,
) -> str:
    timestamp = run_started_at
    if "T" in run_started_at:
        timestamp = run_started_at.split("+")[0].replace(":", "").replace("-", "")[:15]
    context_suffix = " + context" if include_context else ""
    base = f"{timestamp} · {case_id} / {session_id} · {template_id}{context_suffix}"
    if status == "failed" and failed_step:
        return f"{base} · failed at {failed_step}"
    return base


def _first_run_started_at(outputs: list[PipelineRunOutput]) -> str:
    for output in outputs:
        started_at = output.result_record.get("run_started_at")
        if isinstance(started_at, str) and started_at.strip():
            return started_at
    return datetime.now(UTC).isoformat()


def _run_id_from_started_at(run_started_at: str) -> str:
    if "T" in run_started_at:
        compact = run_started_at.split("+")[0].replace(":", "").replace("-", "")
        return compact[:15]
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def save_e2e_run(
    *,
    outputs: list[PipelineRunOutput],
    case_id: str,
    session_id: str,
    template_id: str,
    include_context: bool = False,
    context_case_id: str | None = None,
    status: E2ERunStatus = "complete",
    failed_step: str | None = None,
    error_message: str | None = None,
) -> Path:
    if not outputs:
        raise ValueError("e2e_run_outputs_empty")

    run_started_at = _first_run_started_at(outputs)
    run_id = _run_id_from_started_at(run_started_at)
    run_finished_at = datetime.now(UTC).isoformat()

    manifest_path = (
        E2E_RUNS_DIR
        / f"{run_id}_e2e_{case_id}_{session_id}.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "run_id": run_id,
        "status": status,
        "run_started_at": run_started_at,
        "run_finished_at": run_finished_at,
        "case_id": case_id,
        "session_id": session_id,
        "template_id": template_id,
        "include_context": include_context,
        "context_case_id": context_case_id,
        "failed_step": failed_step,
        "error_message": error_message,
        "outputs": [
            {
                "step": output.step,
                "output_path": str(output.output_path),
            }
            for output in outputs
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def list_e2e_runs() -> list[E2ERunMeta]:
    if not E2E_RUNS_DIR.is_dir():
        return []

    metas: list[E2ERunMeta] = []
    manifest_paths = sorted(
        E2E_RUNS_DIR.glob("*_e2e_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in manifest_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        run_id = payload.get("run_id")
        case_id = payload.get("case_id")
        session_id = payload.get("session_id")
        template_id = payload.get("template_id")
        run_started_at = payload.get("run_started_at")
        include_context = payload.get("include_context")
        status_raw = payload.get("status", "complete")
        failed_step = payload.get("failed_step")

        if not all(
            isinstance(value, str)
            for value in (run_id, case_id, session_id, template_id, run_started_at)
        ):
            continue

        status: E2ERunStatus = (
            "failed" if status_raw == "failed" else "complete"
        )
        failed_step_str = (
            failed_step if isinstance(failed_step, str) and failed_step.strip() else None
        )

        metas.append(
            E2ERunMeta(
                path=path,
                run_id=run_id,
                label=_run_label(
                    run_started_at=run_started_at,
                    case_id=case_id,
                    session_id=session_id,
                    template_id=template_id,
                    include_context=bool(include_context),
                    status=status,
                    failed_step=failed_step_str,
                ),
                case_id=case_id,
                session_id=session_id,
                template_id=template_id,
                run_started_at=run_started_at,
                include_context=bool(include_context),
                status=status,
                failed_step=failed_step_str,
            )
        )
    return metas


def load_e2e_run_outputs(manifest_path: Path) -> list[dict[str, object]]:
    return load_e2e_run(manifest_path).outputs


def load_e2e_run(manifest_path: Path) -> LoadedE2ERun:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("e2e_manifest_must_be_object")

    outputs_raw = payload.get("outputs")
    if not isinstance(outputs_raw, list):
        raise ValueError("e2e_manifest_outputs_missing")

    status_raw = payload.get("status", "complete")
    status: E2ERunStatus = "failed" if status_raw == "failed" else "complete"
    failed_step = payload.get("failed_step")
    error_message = payload.get("error_message")
    failed_step_str = (
        failed_step if isinstance(failed_step, str) and failed_step.strip() else None
    )
    error_message_str = (
        error_message
        if isinstance(error_message, str) and error_message.strip()
        else None
    )

    clustering_output_path = ""
    for entry in outputs_raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("step") == "clustering":
            output_path = entry.get("output_path")
            if isinstance(output_path, str):
                clustering_output_path = output_path

    persisted: list[dict[str, object]] = []
    for entry in outputs_raw:
        if not isinstance(entry, dict):
            raise ValueError("e2e_manifest_output_entry_invalid")

        step = entry.get("step")
        output_path_raw = entry.get("output_path")
        if not isinstance(step, str) or not isinstance(output_path_raw, str):
            raise ValueError("e2e_manifest_output_entry_invalid")

        output_path = Path(output_path_raw)
        if not output_path.is_file():
            raise FileNotFoundError(f"e2e_step_result_missing: {output_path}")

        result_record = dict(load_result_json(output_path))
        if clustering_output_path and step in {"classification", "generation"}:
            result_record.setdefault(
                "clustering_result_file",
                clustering_output_path,
            )
        persisted.append(
            {
                "step": step,
                "result_record": result_record,
                "output_path": str(output_path),
            }
        )

    if not persisted:
        raise ValueError("e2e_manifest_outputs_empty")
    return LoadedE2ERun(
        manifest_path=manifest_path,
        status=status,
        failed_step=failed_step_str,
        error_message=error_message_str,
        outputs=persisted,
    )


__all__ = [
    "E2E_RUNS_DIR",
    "E2ERunMeta",
    "E2ERunStatus",
    "LoadedE2ERun",
    "list_e2e_runs",
    "load_e2e_run",
    "load_e2e_run_outputs",
    "save_e2e_run",
]
