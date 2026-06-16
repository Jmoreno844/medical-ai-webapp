from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from document_pipeline_core.package_root import CORE_PACKAGE_ROOT

CONTEXT_PIPELINE_SUBSTEPS: tuple[str, ...] = (
    "context_triage",
    "context_filter_spans",
    "context_document_directive_filter",
    "context_cluster_spans",
    "context_classify_clusters",
    "context_section_adapter",
)


@dataclass(frozen=True, slots=True)
class PipelineStepSpec:
    step: str
    module_dir: Path
    prompt_stem: str
    default_prompt_version: str
    py_prompt_step: str | None = None
    structured_output_versions: frozenset[str] = field(default_factory=frozenset)
    ui_aliases: frozenset[str] = field(default_factory=frozenset)
    results_module_dir: Path | None = None

    @property
    def prompts_dir(self) -> Path:
        return self.module_dir / "prompts"

    @property
    def results_dir(self) -> Path:
        base = self.results_module_dir or self.module_dir
        return base / "results"

    @property
    def registry_step(self) -> str:
        return self.py_prompt_step or self.step


def _spec(
    step: str,
    module_parts: tuple[str, ...],
    prompt_stem: str,
    default_version: str,
    *,
    py_prompt_step: str | None = None,
    structured_output_versions: frozenset[str] | None = None,
    ui_aliases: frozenset[str] | None = None,
    results_module_parts: tuple[str, ...] | None = None,
) -> PipelineStepSpec:
    module_dir = CORE_PACKAGE_ROOT.joinpath(*module_parts)
    results_module_dir = (
        CORE_PACKAGE_ROOT.joinpath(*results_module_parts)
        if results_module_parts is not None
        else None
    )
    return PipelineStepSpec(
        step=step,
        module_dir=module_dir,
        prompt_stem=prompt_stem,
        default_prompt_version=default_version,
        py_prompt_step=py_prompt_step,
        structured_output_versions=structured_output_versions or frozenset(),
        ui_aliases=ui_aliases or frozenset(),
        results_module_dir=results_module_dir,
    )


_PIPELINE_STEP_SPECS: dict[str, PipelineStepSpec] = {}


def _register(spec: PipelineStepSpec) -> PipelineStepSpec:
    _PIPELINE_STEP_SPECS[spec.step] = spec
    for alias in spec.ui_aliases:
        _PIPELINE_STEP_SPECS[alias] = spec
    return spec


_register(
    _spec(
        "filtering",
        ("filtering",),
        "filtering",
        "v002",
        structured_output_versions=frozenset({"v002"}),
    )
)
_register(
    _spec(
        "clustering",
        ("clustering",),
        "clustering",
        "v002",
        structured_output_versions=frozenset({"v002"}),
    )
)
_register(
    _spec(
        "clustering_repair",
        ("clustering",),
        "clustering_repair",
        "v002",
        py_prompt_step="clustering_repair",
        structured_output_versions=frozenset({"v002"}),
    )
)
_register(
    _spec(
        "classification",
        ("classification",),
        "classification",
        "v004",
        structured_output_versions=frozenset({"v004"}),
    )
)
_register(
    _spec(
        "generation_direct",
        ("generation",),
        "generation",
        "v001",
        py_prompt_step="generation_direct",
        structured_output_versions=frozenset({"v001", "v002"}),
    )
)
_register(
    _spec(
        "generation_direct_with_evidence",
        ("generation",),
        "generation_direct_with_evidence",
        "v001",
        py_prompt_step="generation_direct_with_evidence",
        structured_output_versions=frozenset({"v001"}),
    )
)
_register(
    _spec(
        "generation_planner",
        ("generation",),
        "section_planner",
        "v001",
        py_prompt_step="generation_planner",
        structured_output_versions=frozenset({"v001"}),
    )
)
_register(
    _spec(
        "generation_renderer",
        ("generation",),
        "section_renderer",
        "v001",
        py_prompt_step="generation_renderer",
        structured_output_versions=frozenset(),
    )
)
_register(
    _spec(
        "generation_cluster_planner",
        ("generation",),
        "cluster_planner_route",
        "v001",
        py_prompt_step="generation_cluster_planner",
        structured_output_versions=frozenset({"v001"}),
    )
)
_register(
    _spec(
        "generation_cluster_renderer",
        ("generation",),
        "cluster_planner_route",
        "v001",
        py_prompt_step="generation_cluster_renderer",
        structured_output_versions=frozenset(),
    )
)
_register(
    _spec(
        "generation",
        ("generation",),
        "generation",
        "v003",
        py_prompt_step="generation_direct",
        ui_aliases=frozenset(),
    )
)
_register(
    _spec(
        "context_triage",
        ("context_pipeline", "triage"),
        "triage",
        "v001",
        structured_output_versions=frozenset({"v001"}),
    )
)
_register(
    _spec(
        "context_filter_spans",
        ("context_pipeline", "filter_spans"),
        "filter_spans",
        "v002",
        structured_output_versions=frozenset({"v002"}),
    )
)
_register(
    _spec(
        "context_document_directive_filter",
        ("context_pipeline", "document_directive_filter"),
        "span_selector",
        "v001",
        py_prompt_step="context_document_directive_filter",
        structured_output_versions=frozenset({"v001"}),
    )
)
_register(
    _spec(
        "context_cluster_spans",
        ("context_pipeline", "cluster_spans"),
        "cluster_spans",
        "v002",
        structured_output_versions=frozenset({"v002"}),
    )
)
_register(
    _spec(
        "context_classify_clusters",
        ("context_pipeline", "classify_clusters"),
        "classify_clusters",
        "v002",
        structured_output_versions=frozenset({"v002"}),
    )
)
_register(
    _spec(
        "context_section_adapter",
        ("context_pipeline", "section_adapter"),
        "section_adapter",
        "v003",
        structured_output_versions=frozenset({"v003"}),
    )
)
_register(
    _spec(
        "context_pipeline",
        ("context_pipeline", "section_adapter"),
        "section_adapter",
        "v001",
        ui_aliases=frozenset(),
        results_module_parts=("context_pipeline", "section_adapter"),
    )
)
_PIPELINE_STEP_SPECS["context_ad_hoc_pipeline"] = _PIPELINE_STEP_SPECS["context_pipeline"]


def get_step_spec(step: str) -> PipelineStepSpec:
    spec = _PIPELINE_STEP_SPECS.get(step)
    if spec is None:
        raise ValueError(f"unknown_pipeline_step: {step}")
    return spec


def list_registered_steps(*, include_aliases: bool = False) -> list[str]:
    if include_aliases:
        return sorted(_PIPELINE_STEP_SPECS)
    seen: set[str] = set()
    steps: list[str] = []
    for spec in _PIPELINE_STEP_SPECS.values():
        if spec.step in seen:
            continue
        seen.add(spec.step)
        steps.append(spec.step)
    return sorted(steps)


def default_prompt_version(step: str) -> str:
    if step in {"context_pipeline", "context_ad_hoc_pipeline"}:
        return get_step_spec(step).default_prompt_version
    return get_step_spec(step).default_prompt_version


def default_context_substep_versions() -> dict[str, str]:
    return {substep: default_prompt_version(substep) for substep in CONTEXT_PIPELINE_SUBSTEPS}


__all__ = [
    "CORE_PACKAGE_ROOT",
    "CONTEXT_PIPELINE_SUBSTEPS",
    "PipelineStepSpec",
    "default_context_substep_versions",
    "default_prompt_version",
    "get_step_spec",
    "list_registered_steps",
]
