from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from document_pipeline_core.classification.batching import count_text_tokens
from document_pipeline_core.common.templates import DEFAULT_TEMPLATES_DIR, load_template

if TYPE_CHECKING:
    from document_pipeline_core.common.usage_cost import TokenUsage


@dataclass(frozen=True, slots=True)
class CostProjectionSettings:
    use_cache_pricing: bool = False
    include_template_in_cache: bool = True


def effective_cached_input_tokens(
    usage: TokenUsage,
    *,
    projected_cacheable_tokens: int,
    settings: CostProjectionSettings,
) -> int:
    if not settings.use_cache_pricing:
        return 0
    projected = max(usage.cached_input_tokens, max(0, projected_cacheable_tokens))
    return min(usage.input_tokens, projected)


def _prompt_version_from_record(result_record: dict[str, object]) -> str:
    prompt_version = result_record.get("prompt_version")
    if isinstance(prompt_version, str) and prompt_version.strip():
        return prompt_version.strip().lower()
    return "v001"


def _template_id_from_record(result_record: dict[str, object]) -> str | None:
    template_id = result_record.get("template_id")
    if isinstance(template_id, str) and template_id.strip():
        return template_id.strip()
    return None


def _count_json_tokens(payload: object) -> int:
    return count_text_tokens(json.dumps(payload, ensure_ascii=False, indent=2))


@lru_cache(maxsize=32)
def _count_prompt_file_tokens(path: str) -> int:
    from pathlib import Path

    prompt_path = Path(path)
    if not prompt_path.is_file():
        return 0
    return count_text_tokens(prompt_path.read_text(encoding="utf-8"))


def _classification_cacheable_tokens(
    result_record: dict[str, object],
    *,
    include_template: bool,
) -> int:
    from document_pipeline_core.classification.lib import (
        classification_uses_enriched_system_prompt,
        load_classification_prompt,
        prepare_classification_prompts,
    )

    prompt_version = _prompt_version_from_record(result_record)
    base_prompt = load_classification_prompt(prompt_version)
    base_tokens = count_text_tokens(base_prompt)

    if not include_template:
        return base_tokens

    template_id = _template_id_from_record(result_record)
    if template_id is None:
        return base_tokens

    template = load_template(template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    if classification_uses_enriched_system_prompt(prompt_version):
        system_prompt, _ = prepare_classification_prompts(
            base_prompt,
            template,
            prompt_version=prompt_version,
        )
        return count_text_tokens(system_prompt)

    return base_tokens + _count_json_tokens(template.to_prompt_payload())


def _generation_cacheable_tokens(
    result_record: dict[str, object],
    *,
    label: str,
    include_template: bool,
) -> int:
    from document_pipeline_core.generation.lib import (
        generation_direct_uses_py_prompt,
        generation_prompt_file_path,
        load_generation_direct_prompt,
    )

    prompt_version = _prompt_version_from_record(result_record)
    if generation_direct_uses_py_prompt(prompt_version):
        tokens = count_text_tokens(load_generation_direct_prompt(prompt_version))
    else:
        prompt_path = generation_prompt_file_path(prompt_version)
        tokens = _count_prompt_file_tokens(str(prompt_path))

    if not include_template:
        return tokens

    template_id = _template_id_from_record(result_record)
    if template_id is None:
        return tokens

    template = load_template(template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    tokens += count_text_tokens(template.generation.guidelines)

    section_id = label.removeprefix("Generation · ").strip()
    section = template.section_by_id(section_id)
    if section is not None:
        tokens += _count_json_tokens(section.to_generation_payload())
    return tokens


def estimate_cacheable_input_tokens(
    *,
    step: str,
    label: str,
    result_record: dict[str, object],
    settings: CostProjectionSettings,
) -> int:
    if not settings.use_cache_pricing:
        return 0

    include_template = settings.include_template_in_cache
    prompt_version = _prompt_version_from_record(result_record)

    if step == "filtering":
        from document_pipeline_core.filtering.lib import filtering_uses_py_prompt, load_filtering_prompt
        from document_pipeline_core.filtering.lib import filtering_prompt_file_path

        if filtering_uses_py_prompt(prompt_version):
            return count_text_tokens(load_filtering_prompt(prompt_version))
        return _count_prompt_file_tokens(
            str(filtering_prompt_file_path(prompt_version))
        )

    if step == "clustering":
        from document_pipeline_core.clustering.lib import clustering_uses_py_prompt, load_clustering_prompt
        from document_pipeline_core.clustering.lib import clustering_prompt_file_path
        from document_pipeline_core.clustering.repair import (
            clustering_repair_uses_py_prompt,
            load_clustering_repair_prompt,
            clustering_repair_prompt_file_path,
        )

        if "repair" in label.lower():
            repair_version = result_record.get("repair_prompt_version", "v001")
            if not isinstance(repair_version, str):
                repair_version = "v001"
            if clustering_repair_uses_py_prompt(repair_version):
                return count_text_tokens(load_clustering_repair_prompt(repair_version))
            return _count_prompt_file_tokens(
                str(clustering_repair_prompt_file_path(repair_version))
            )

        if clustering_uses_py_prompt(prompt_version):
            return count_text_tokens(load_clustering_prompt(prompt_version))
        return _count_prompt_file_tokens(
            str(clustering_prompt_file_path(prompt_version))
        )

    if step == "classification":
        return _classification_cacheable_tokens(
            result_record,
            include_template=include_template,
        )

    if step == "generation":
        return _generation_cacheable_tokens(
            result_record,
            label=label,
            include_template=include_template,
        )

    if step == "context_pipeline":
        context_label = label.removeprefix("Context · ").strip()
        prompt_loaders = {
            "triage": "context_pipeline.triage.lib.triage_prompt_file_path",
            "filter_spans": "context_pipeline.filter_spans.lib.filter_spans_prompt_file_path",
            "cluster_spans": "context_pipeline.cluster_spans.lib.cluster_spans_prompt_file_path",
            "classify_clusters": "context_pipeline.classify_clusters.lib.classify_clusters_prompt_file_path",
            "section_adapter": "context_pipeline.section_adapter.lib.section_adapter_prompt_file_path",
        }
        for key, import_path in prompt_loaders.items():
            if context_label.startswith(key):
                if key == "filter_spans":
                    from document_pipeline_core.context_pipeline.filter_spans.lib import (
                        filter_spans_uses_py_prompt,
                        load_filter_spans_prompt,
                        filter_spans_prompt_file_path,
                    )

                    if filter_spans_uses_py_prompt(prompt_version):
                        return count_text_tokens(load_filter_spans_prompt(prompt_version))
                    return _count_prompt_file_tokens(
                        str(filter_spans_prompt_file_path(prompt_version))
                    )
                if key == "triage":
                    from document_pipeline_core.context_pipeline.triage.lib import (
                        load_triage_prompt,
                        triage_uses_py_prompt,
                        triage_prompt_file_path,
                    )

                    if triage_uses_py_prompt(prompt_version):
                        return count_text_tokens(load_triage_prompt(prompt_version))
                    return _count_prompt_file_tokens(
                        str(triage_prompt_file_path(prompt_version))
                    )
                if key == "classify_clusters":
                    from document_pipeline_core.context_pipeline.classify_clusters.lib import (
                        classify_clusters_uses_py_prompt,
                        load_classify_clusters_prompt,
                        classify_clusters_prompt_file_path,
                    )

                    if classify_clusters_uses_py_prompt(prompt_version):
                        return count_text_tokens(
                            load_classify_clusters_prompt(prompt_version)
                        )
                    return _count_prompt_file_tokens(
                        str(classify_clusters_prompt_file_path(prompt_version))
                    )
                module_name, func_name = import_path.rsplit(".", 1)
                import importlib

                module = importlib.import_module(module_name)
                prompt_file_path = getattr(module, func_name)
                return _count_prompt_file_tokens(str(prompt_file_path(prompt_version)))
        from document_pipeline_core.context_pipeline.section_adapter.lib import section_adapter_prompt_file_path

        return _count_prompt_file_tokens(
            str(section_adapter_prompt_file_path(prompt_version))
        )

    return 0


__all__ = [
    "CostProjectionSettings",
    "effective_cached_input_tokens",
    "estimate_cacheable_input_tokens",
]
