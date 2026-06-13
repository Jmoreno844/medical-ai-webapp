from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from classification.lib import DEFAULT_CASES_INDEX, load_cluster_cases
from common.templates import DEFAULT_TEMPLATES_DIR, list_template_ids
from common.transcripts import TranscriptCase, build_turn_catalog, load_cases

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]

MODULE_DIRS = {
    "filtering": AI_PIPELINE_ROOT / "filtering",
    "clustering": AI_PIPELINE_ROOT / "clustering",
    "classification": AI_PIPELINE_ROOT / "classification",
    "generation": AI_PIPELINE_ROOT / "generation",
    "context_decompose": AI_PIPELINE_ROOT / "context_pipeline" / "decompose",
    "context_extract": AI_PIPELINE_ROOT / "context_pipeline" / "extract",
    "context_classify_claims": (
        AI_PIPELINE_ROOT / "context_pipeline" / "classify_claims"
    ),
}

PROMPT_STEMS = {
    "filtering": "filtering",
    "clustering": "clustering",
    "classification": "classification",
    "generation": "generation",
    "context_decompose": "decompose",
    "context_extract": "extract",
    "context_classify_claims": "classify_claims",
}

DEFAULT_PROMPT_VERSIONS = {
    "filtering": "v001",
    "clustering": "v001",
    "classification": "v002",
    "generation": "v001",
    "context_decompose": "v001",
    "context_extract": "v001",
    "context_classify_claims": "v001",
}

PROMPT_VERSION_PATTERN = re.compile(r"^v\d{3}$")


@dataclass(frozen=True, slots=True)
class TranscriptCaseMeta:
    case_id: str
    notes: str | None
    turn_count: int


@dataclass(frozen=True, slots=True)
class ClassificationSessionMeta:
    session_id: str
    cluster_count: int
    template_id: str


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
    index_path = cases_index or (AI_PIPELINE_ROOT / "cases" / "index.json")
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
    cases = load_cases(AI_PIPELINE_ROOT / "cases" / "index.json")
    for case in cases:
        if case.id == case_id:
            return case
    raise ValueError(f"transcript_case_not_found: {case_id}")


def list_classification_sessions() -> list[ClassificationSessionMeta]:
    clusters = load_cluster_cases(DEFAULT_CASES_INDEX)
    sessions: dict[str, list[str]] = {}
    templates: dict[str, str] = {}
    for cluster in clusters:
        session_id = cluster.id.split("_", 1)[0]
        sessions.setdefault(session_id, []).append(cluster.id)
        templates[session_id] = cluster.template_id
    return [
        ClassificationSessionMeta(
            session_id=session_id,
            cluster_count=len(cluster_ids),
            template_id=templates[session_id],
        )
        for session_id, cluster_ids in sorted(sessions.items())
    ]


def list_templates() -> list[str]:
    return list_template_ids(templates_dir=DEFAULT_TEMPLATES_DIR)


def list_context_cases() -> list[str]:
    from context_pipeline.decompose.lib import load_context_cases

    index_path = AI_PIPELINE_ROOT / "context_pipeline" / "cases" / "index.json"
    return [case.id for case in load_context_cases(index_path)]


def list_prompt_versions(step: str) -> list[str]:
    module_dir = MODULE_DIRS.get(step)
    if module_dir is None:
        raise ValueError(f"unknown_pipeline_step: {step}")
    prompts_dir = module_dir / "prompts"
    stem = PROMPT_STEMS[step]
    if not prompts_dir.is_dir():
        return [DEFAULT_PROMPT_VERSIONS[step]]
    versions = sorted(
        path.stem.removeprefix(f"{stem}_")
        for path in prompts_dir.glob(f"{stem}_v*.txt")
        if PROMPT_VERSION_PATTERN.fullmatch(path.stem.removeprefix(f"{stem}_"))
    )
    return versions or [DEFAULT_PROMPT_VERSIONS[step]]


def default_prompt_version(step: str) -> str:
    versions = list_prompt_versions(step)
    preferred = DEFAULT_PROMPT_VERSIONS.get(step)
    if preferred in versions:
        return preferred
    return versions[0]


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
    module_dir = MODULE_DIRS.get(step)
    if module_dir is None:
        raise ValueError(f"unknown_pipeline_step: {step}")
    results_dir = module_dir / "results"
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
    "default_prompt_version",
    "list_classification_sessions",
    "list_prompt_versions",
    "list_results",
    "list_templates",
    "list_transcript_cases",
    "load_result_json",
    "load_transcript_case",
]
