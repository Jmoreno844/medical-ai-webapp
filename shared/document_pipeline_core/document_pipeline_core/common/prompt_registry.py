from __future__ import annotations

import importlib
from types import ModuleType

from document_pipeline_core.common.prompts import normalize_prompt_version

_CORE = "document_pipeline_core"

PY_PROMPTS: dict[str, dict[str, str]] = {
    "classification": {
        "v004": f"{_CORE}.classification.prompts.classification_prompt_v001",
    },
    "filtering": {
        "v002": f"{_CORE}.filtering.prompts.filtering_prompt_v001",
    },
    "clustering": {
        "v002": f"{_CORE}.clustering.prompts.clustering_prompt_v001",
    },
    "clustering_repair": {
        "v002": f"{_CORE}.clustering.prompts.clustering_repair_prompt_v001",
    },
    "context_triage": {
        "v001": f"{_CORE}.context_pipeline.triage.prompts.triage_prompt_v001",
    },
    "context_filter_spans": {
        "v002": f"{_CORE}.context_pipeline.filter_spans.prompts.filter_spans_prompt_v001",
    },
    "context_classify_clusters": {
        "v002": f"{_CORE}.context_pipeline.classify_clusters.prompts.classify_clusters_prompt_v001",
    },
    "context_cluster_spans": {
        "v002": f"{_CORE}.context_pipeline.cluster_spans.prompts.cluster_spans_prompt_v001",
    },
    "context_document_directive_filter": {
        "v001": f"{_CORE}.context_pipeline.document_directive_filter.prompts.span_selector_prompt_v001",
    },
    "context_section_adapter": {
        "v003": f"{_CORE}.context_pipeline.section_adapter.prompts.adapter_prompt_v001",
    },
    "generation_direct": {
        "v001": f"{_CORE}.generation.prompts.direct.generation_direct_prompt_v001",
    },
    "generation_planner": {
        "v001": f"{_CORE}.generation.prompts.two_step.section_planner_prompt_v001",
    },
    "generation_renderer": {
        "v001": f"{_CORE}.generation.prompts.two_step.section_renderer_prompt_v001",
    },
}


def py_prompt_versions(step: str) -> list[str]:
    return sorted(PY_PROMPTS.get(step, {}).keys())


def is_py_prompt_version(step: str, version: str) -> bool:
    normalized = normalize_prompt_version(version)
    return normalized in PY_PROMPTS.get(step, {})


def load_py_prompt_module(step: str, version: str) -> ModuleType:
    normalized = normalize_prompt_version(version)
    module_path = PY_PROMPTS.get(step, {}).get(normalized)
    if module_path is None:
        raise ValueError(f"ai_pipeline_py_prompt_not_registered: {step}:{normalized}")
    return importlib.import_module(module_path)


def py_system_prompt(step: str, version: str) -> str:
    module = load_py_prompt_module(step, version)
    system_prompt = getattr(module, "SYSTEM_PROMPT", None)
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError(f"ai_pipeline_py_prompt_missing_system_prompt: {step}:{version}")
    return system_prompt.strip()


__all__ = [
    "PY_PROMPTS",
    "is_py_prompt_version",
    "load_py_prompt_module",
    "py_prompt_versions",
    "py_system_prompt",
]
