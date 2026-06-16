from __future__ import annotations

import pytest

from document_pipeline_core.common.prompt_registry import (
    is_py_prompt_version,
    load_py_prompt_module,
    py_prompt_versions,
    py_system_prompt,
)


def test_py_prompt_versions_includes_filtering_v002() -> None:
    assert "v002" in py_prompt_versions("filtering")


def test_py_prompt_versions_includes_clustering_v002() -> None:
    assert "v002" in py_prompt_versions("clustering")


def test_load_py_prompt_module_filtering_v002() -> None:
    module = load_py_prompt_module("filtering", "v002")
    assert module.__name__ == "document_pipeline_core.filtering.prompts.filtering_prompt_v001"


def test_load_py_prompt_module_clustering_v002() -> None:
    module = load_py_prompt_module("clustering", "v002")
    assert module.__name__ == "document_pipeline_core.clustering.prompts.clustering_prompt_v001"


def test_py_prompt_versions_includes_clustering_repair_v002() -> None:
    assert "v002" in py_prompt_versions("clustering_repair")


def test_py_prompt_versions_includes_context_filter_spans_v002() -> None:
    assert "v002" in py_prompt_versions("context_filter_spans")


def test_load_py_prompt_module_clustering_repair_v002() -> None:
    module = load_py_prompt_module("clustering_repair", "v002")
    assert module.__name__ == "document_pipeline_core.clustering.prompts.clustering_repair_prompt_v001"


def test_py_prompt_versions_includes_context_classify_clusters_v002() -> None:
    assert "v002" in py_prompt_versions("context_classify_clusters")


def test_load_py_prompt_module_context_classify_clusters_v002() -> None:
    module = load_py_prompt_module("context_classify_clusters", "v002")
    assert (
        module.__name__
        == "document_pipeline_core.context_pipeline.classify_clusters.prompts.classify_clusters_prompt_v001"
    )


def test_load_py_prompt_module_context_filter_spans_v002() -> None:
    module = load_py_prompt_module("context_filter_spans", "v002")
    assert (
        module.__name__
        == "document_pipeline_core.context_pipeline.filter_spans.prompts.filter_spans_prompt_v001"
    )


def test_py_prompt_versions_includes_classification_v004() -> None:
    assert "v004" in py_prompt_versions("classification")


def test_is_py_prompt_version_classification_v004() -> None:
    assert is_py_prompt_version("classification", "v004")
    assert not is_py_prompt_version("classification", "v003")
    assert not is_py_prompt_version("filtering", "v004")


def test_load_py_prompt_module_classification_v004() -> None:
    module = load_py_prompt_module("classification", "v004")
    assert module.__name__ == "document_pipeline_core.classification.prompts.classification_prompt_v001"
    assert isinstance(module.SYSTEM_PROMPT, str)
    assert module.SYSTEM_PROMPT.strip()


def test_py_system_prompt_classification_v004() -> None:
    prompt = py_system_prompt("classification", "v004")
    assert "# Identity" in prompt
    assert "JSON only" in prompt or "JSON" in prompt


def test_load_py_prompt_module_unknown_raises() -> None:
    with pytest.raises(ValueError, match="ai_pipeline_py_prompt_not_registered"):
        load_py_prompt_module("classification", "v999")


def test_py_prompt_versions_includes_context_triage_v001() -> None:
    assert "v001" in py_prompt_versions("context_triage")


def test_load_py_prompt_module_context_triage_v001() -> None:
    module = load_py_prompt_module("context_triage", "v001")
    assert (
        module.__name__
        == "document_pipeline_core.context_pipeline.triage.prompts.triage_prompt_v001"
    )


def test_py_prompt_versions_includes_context_cluster_spans_v002() -> None:
    assert "v002" in py_prompt_versions("context_cluster_spans")


def test_load_py_prompt_module_context_cluster_spans_v002() -> None:
    module = load_py_prompt_module("context_cluster_spans", "v002")
    assert (
        module.__name__
        == "document_pipeline_core.context_pipeline.cluster_spans.prompts.cluster_spans_prompt_v001"
    )


def test_py_prompt_versions_includes_context_section_adapter_v003() -> None:
    assert "v003" in py_prompt_versions("context_section_adapter")


def test_load_py_prompt_module_context_section_adapter_v003() -> None:
    module = load_py_prompt_module("context_section_adapter", "v003")
    assert (
        module.__name__
        == "document_pipeline_core.context_pipeline.section_adapter.prompts.adapter_prompt_v001"
    )
