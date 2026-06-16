from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from document_pipeline_core.classification.lib import load_cluster_cases
from document_pipeline_core.common.pipeline_steps import get_step_spec, list_registered_steps
from document_pipeline_core.common.prompt_registry import py_prompt_versions
from document_pipeline_core.common.prompt_runtime import list_prompt_versions as runtime_list_prompt_versions
from document_pipeline_core.common.prompt_runtime import resolve_prompt_version
from document_pipeline_core.common.templates import (
    DEFAULT_TEMPLATES_DIR,
    list_template_ids,
    template_supports_hybrid_generation_by_id,
)
from document_pipeline_core.common.transcripts import TranscriptCase, build_turn_catalog, load_cases
from document_pipeline_core.package_root import PACKAGE_ROOT

from harness.context_cases import load_context_cases, select_context_case
from harness.paths import (
    AI_PIPELINE_ROOT,
    CLUSTER_CASES_INDEX,
    CONTEXT_CASES_INDEX,
    TRANSCRIPT_CASES_INDEX,
    harness_results_dir,
)

_REGISTERED_STEPS = list_registered_steps(include_aliases=True)
MODULE_DIRS = {
    step: AI_PIPELINE_ROOT / get_step_spec(step).module_dir.relative_to(PACKAGE_ROOT)
    for step in _REGISTERED_STEPS
}
PROMPT_STEMS = {step: get_step_spec(step).prompt_stem for step in _REGISTERED_STEPS}
DEFAULT_PROMPT_VERSIONS = {
    step: get_step_spec(step).default_prompt_version for step in _REGISTERED_STEPS
}


@dataclass(frozen=True, slots=True)
class TranscriptCaseMeta:
    case_id: str
    notes: str | None
    turn_count: int


@dataclass(frozen=True, slots=True)
class ClassificationSessionMeta:
    session_id: str
    cluster_count: int


@dataclass(frozen=True, slots=True)
class ResultMeta:
    path: Path
    step: str
    label: str
    case_id: str | None
    session_id: str | None
    provider: str | None
    model: str | None
    run_started_at: str | None


def list_transcript_cases(
    *,
    cases_index: Path | None = None,
) -> list[TranscriptCaseMeta]:
    index_path = cases_index or TRANSCRIPT_CASES_INDEX
    cases = load_cases(index_path)
    return [
        TranscriptCaseMeta(
            case_id=case.id,
            notes=case.notes,
            turn_count=len(build_turn_catalog(case.transcript_json)),
        )
        for case in cases
    ]


def load_transcript_case(case_id: str) -> TranscriptCase:
    cases = load_cases(TRANSCRIPT_CASES_INDEX)
    for case in cases:
        if case.id == case_id:
            return case
    raise ValueError(f"transcript_case_not_found: {case_id}")


def _extract_transcript_payload(payload: dict[str, object]) -> tuple[dict[str, object], str | None, str | None]:
    if "chunks" in payload:
        return payload, None, None

    transcript_json = payload.get("transcript_json")
    if isinstance(transcript_json, dict) and "chunks" in transcript_json:
        notes = payload.get("notes")
        index_id = payload.get("id")
        return (
            transcript_json,
            notes.strip() if isinstance(notes, str) and notes.strip() else None,
            index_id.strip() if isinstance(index_id, str) and index_id.strip() else None,
        )

    raise ValueError(
        "Formato no reconocido. Usa un JSON con chunks[] o transcript_json.chunks[] "
        "(como ai-pipeline/cases/transcripts/)."
    )


def parse_transcript_case_from_json(
    raw: str | dict[str, object],
    *,
    case_id: str | None = None,
) -> TranscriptCase:
    if isinstance(raw, str):
        normalized = raw.strip()
        if not normalized:
            raise ValueError("El JSON pegado está vacío.")
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido: {exc}") from exc
    else:
        payload = raw

    if not isinstance(payload, dict):
        raise ValueError("El case debe ser un objeto JSON.")

    transcript_payload, notes, index_id = _extract_transcript_payload(payload)
    chunks = transcript_payload.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("El case debe incluir al menos un chunk con turnos.")

    catalog = build_turn_catalog(transcript_payload)
    if not catalog:
        raise ValueError("El case no contiene turnos con speaker y text válidos.")

    resolved_id = (case_id or index_id or "").strip()
    if not resolved_id:
        session_id = transcript_payload.get("session_id")
        if isinstance(session_id, str) and session_id.strip():
            resolved_id = session_id.strip()
        else:
            resolved_id = "pasted_transcript"

    return TranscriptCase(
        id=resolved_id,
        transcript_json=transcript_payload,
        notes=notes,
    )


def list_classification_sessions() -> list[ClassificationSessionMeta]:
    clusters = load_cluster_cases(CLUSTER_CASES_INDEX)
    sessions: dict[str, list[str]] = {}
    for cluster in clusters:
        session_id = cluster.id.split("_", 1)[0]
        sessions.setdefault(session_id, []).append(cluster.id)
    return [
        ClassificationSessionMeta(
            session_id=session_id,
            cluster_count=len(cluster_ids),
        )
        for session_id, cluster_ids in sorted(sessions.items())
    ]


def list_templates() -> list[str]:
    return list_template_ids(templates_dir=DEFAULT_TEMPLATES_DIR)


def list_context_cases() -> list[str]:
    return [case.id for case in load_context_cases(CONTEXT_CASES_INDEX)]


def list_context_case_document_files(context_case_id: str) -> list[str]:
    case_meta = select_context_case(
        load_context_cases(CONTEXT_CASES_INDEX),
        case_id=context_case_id,
    )
    return list(case_meta.document_files)


def list_prompt_versions(step: str) -> list[str]:
    return runtime_list_prompt_versions(step)


def list_harness_prompt_versions(step: str) -> list[str]:
    spec = get_step_spec(step)
    py_versions = py_prompt_versions(spec.registry_step)
    if py_versions:
        return py_versions
    return list_prompt_versions(step)


def default_harness_prompt_version(step: str) -> str:
    versions = list_harness_prompt_versions(step)
    preferred = default_prompt_version(step)
    return preferred if preferred in versions else versions[0]


def list_generation_prompt_versions(*, generation_route: str) -> list[str]:
    normalized = generation_route.strip().lower()
    if normalized == "two_step":
        planner = set(py_prompt_versions("generation_planner"))
        renderer = set(py_prompt_versions("generation_renderer"))
        shared = sorted(planner & renderer)
        if shared:
            return shared
        return sorted(planner or renderer)
    if normalized == "cluster_planner":
        planner = set(py_prompt_versions("generation_cluster_planner"))
        renderer = set(py_prompt_versions("generation_cluster_renderer"))
        shared = sorted(planner & renderer)
        if shared:
            return shared
        return sorted(planner or renderer)
    if normalized == "direct_with_evidence":
        return sorted(py_prompt_versions("generation_direct_with_evidence"))
    if normalized == "hybrid":
        direct_evidence = set(py_prompt_versions("generation_direct_with_evidence"))
        cluster_planner = set(py_prompt_versions("generation_cluster_planner"))
        cluster_renderer = set(py_prompt_versions("generation_cluster_renderer"))
        shared_cluster = cluster_planner & cluster_renderer
        shared = sorted(direct_evidence & shared_cluster)
        if shared:
            return shared
        return sorted(direct_evidence or shared_cluster)
    return ["v001"]


def template_supports_hybrid(template_id: str) -> bool:
    return template_supports_hybrid_generation_by_id(template_id)


def list_generation_prompt_versions_legacy(*, linked_evidence_two_step: bool) -> list[str]:
    route = "two_step" if linked_evidence_two_step else "direct"
    return list_generation_prompt_versions(generation_route=route)


def default_generation_prompt_version(*, generation_route: str) -> str:
    return list_generation_prompt_versions(generation_route=generation_route)[0]


def default_generation_prompt_version_legacy(*, linked_evidence_two_step: bool) -> str:
    return default_generation_prompt_version(
        generation_route="two_step" if linked_evidence_two_step else "direct",
    )


def default_prompt_version(step: str) -> str:
    return resolve_prompt_version(step)


def _result_label(
    *,
    path: Path,
    payload: dict[str, object],
    step: str,
) -> str:
    run_started_at = payload.get("run_started_at")
    timestamp = path.stem.split("_", 1)[0] if path.stem else path.name
    if isinstance(run_started_at, str) and "T" in run_started_at:
        timestamp = run_started_at.split("+")[0].replace(":", "").replace("-", "")[:15]

    case_id = payload.get("case_id")
    session_id = payload.get("session_id")
    subject = case_id if isinstance(case_id, str) else session_id
    provider = payload.get("provider")
    model = payload.get("model")
    model_part = ""
    if isinstance(provider, str) and isinstance(model, str):
        model_part = f" · {provider}/{model}"
    elif isinstance(provider, str):
        model_part = f" · {provider}"

    subject_part = subject if isinstance(subject, str) else step
    return f"{timestamp} · {subject_part}{model_part}"


def list_results(step: str) -> list[ResultMeta]:
    results_dir = harness_results_dir(step)
    if not results_dir.is_dir():
        return []

    metas: list[ResultMeta] = []
    result_paths = sorted(
        results_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in result_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        case_id = payload.get("case_id")
        session_id = payload.get("session_id")
        metas.append(
            ResultMeta(
                path=path,
                step=step,
                label=_result_label(path=path, payload=payload, step=step),
                case_id=case_id if isinstance(case_id, str) else None,
                session_id=session_id if isinstance(session_id, str) else None,
                provider=payload.get("provider")
                if isinstance(payload.get("provider"), str)
                else None,
                model=payload.get("model")
                if isinstance(payload.get("model"), str)
                else None,
                run_started_at=payload.get("run_started_at")
                if isinstance(payload.get("run_started_at"), str)
                else None,
            )
        )
    return metas


def load_result_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pipeline_result_must_be_object")
    return payload


__all__ = [
    "AI_PIPELINE_ROOT",
    "DEFAULT_PROMPT_VERSIONS",
    "ClassificationSessionMeta",
    "MODULE_DIRS",
    "PROMPT_STEMS",
    "ResultMeta",
    "TranscriptCaseMeta",
    "default_generation_prompt_version",
    "default_harness_prompt_version",
    "default_prompt_version",
    "list_classification_sessions",
    "list_context_case_document_files",
    "list_context_cases",
    "list_generation_prompt_versions",
    "list_harness_prompt_versions",
    "template_supports_hybrid",
    "list_prompt_versions",
    "list_results",
    "list_templates",
    "list_transcript_cases",
    "load_result_json",
    "load_transcript_case",
    "parse_transcript_case_from_json",
]
