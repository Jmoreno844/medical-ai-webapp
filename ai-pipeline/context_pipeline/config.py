from __future__ import annotations

from dataclasses import dataclass

from common.pipeline_steps import CONTEXT_PIPELINE_SUBSTEPS, default_context_substep_versions
from common.prompt_runtime import load_system_prompt, prompt_reference, resolve_prompt_version


@dataclass(frozen=True, slots=True)
class ContextPipelineConfig:
    prompt_versions: dict[str, str]

    @classmethod
    def with_defaults(
        cls,
        overrides: dict[str, str] | None = None,
    ) -> ContextPipelineConfig:
        versions = default_context_substep_versions()
        if overrides:
            for step, version in overrides.items():
                if step in CONTEXT_PIPELINE_SUBSTEPS and version.strip():
                    versions[step] = resolve_prompt_version(step, version)
        return cls(prompt_versions=versions)


@dataclass(frozen=True, slots=True)
class ResolvedStepPrompt:
    step: str
    system_prompt: str
    prompt_version: str
    prompt_reference: str


@dataclass(frozen=True, slots=True)
class ContextPipelinePromptBundle:
    triage: ResolvedStepPrompt
    filter_spans: ResolvedStepPrompt
    document_directive_filter: ResolvedStepPrompt
    cluster_spans: ResolvedStepPrompt
    classify_clusters: ResolvedStepPrompt
    section_adapter: ResolvedStepPrompt

    def versions_by_step(self) -> dict[str, str]:
        return {
            self.triage.step: self.triage.prompt_version,
            self.filter_spans.step: self.filter_spans.prompt_version,
            self.document_directive_filter.step: self.document_directive_filter.prompt_version,
            self.cluster_spans.step: self.cluster_spans.prompt_version,
            self.classify_clusters.step: self.classify_clusters.prompt_version,
            self.section_adapter.step: self.section_adapter.prompt_version,
        }

    def references_by_step(self) -> dict[str, str]:
        return {
            self.triage.step: self.triage.prompt_reference,
            self.filter_spans.step: self.filter_spans.prompt_reference,
            self.document_directive_filter.step: self.document_directive_filter.prompt_reference,
            self.cluster_spans.step: self.cluster_spans.prompt_reference,
            self.classify_clusters.step: self.classify_clusters.prompt_reference,
            self.section_adapter.step: self.section_adapter.prompt_reference,
        }


def _resolve_step_prompt(step: str, version: str) -> ResolvedStepPrompt:
    resolved_version = resolve_prompt_version(step, version)
    return ResolvedStepPrompt(
        step=step,
        system_prompt=load_system_prompt(step, resolved_version),
        prompt_version=resolved_version,
        prompt_reference=prompt_reference(step, resolved_version),
    )


def build_context_pipeline_prompt_bundle(
    config: ContextPipelineConfig,
) -> ContextPipelinePromptBundle:
    versions = config.prompt_versions
    return ContextPipelinePromptBundle(
        triage=_resolve_step_prompt("context_triage", versions["context_triage"]),
        filter_spans=_resolve_step_prompt(
            "context_filter_spans", versions["context_filter_spans"]
        ),
        document_directive_filter=_resolve_step_prompt(
            "context_document_directive_filter",
            versions["context_document_directive_filter"],
        ),
        cluster_spans=_resolve_step_prompt(
            "context_cluster_spans", versions["context_cluster_spans"]
        ),
        classify_clusters=_resolve_step_prompt(
            "context_classify_clusters", versions["context_classify_clusters"]
        ),
        section_adapter=_resolve_step_prompt(
            "context_section_adapter", versions["context_section_adapter"]
        ),
    )


__all__ = [
    "ContextPipelineConfig",
    "ContextPipelinePromptBundle",
    "ResolvedStepPrompt",
    "build_context_pipeline_prompt_bundle",
]
