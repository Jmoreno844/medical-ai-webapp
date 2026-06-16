from __future__ import annotations

from ui.discovery import DEFAULT_PROMPT_VERSIONS, default_prompt_version, list_prompt_versions


def test_default_classification_prompt_version_is_v004() -> None:
    assert DEFAULT_PROMPT_VERSIONS["classification"] == "v004"
    assert default_prompt_version("classification") == "v004"


def test_default_filtering_prompt_version_is_v002() -> None:
    assert DEFAULT_PROMPT_VERSIONS["filtering"] == "v002"
    assert default_prompt_version("filtering") == "v002"


def test_list_filtering_prompt_versions_includes_v002() -> None:
    versions = list_prompt_versions("filtering")
    assert "v001" in versions
    assert "v002" in versions


def test_default_clustering_prompt_version_is_v002() -> None:
    assert DEFAULT_PROMPT_VERSIONS["clustering"] == "v002"
    assert default_prompt_version("clustering") == "v002"


def test_list_clustering_prompt_versions_includes_v002() -> None:
    versions = list_prompt_versions("clustering")
    assert "v001" in versions
    assert "v002" in versions


def test_default_context_filter_spans_prompt_version_is_v002() -> None:
    assert DEFAULT_PROMPT_VERSIONS["context_filter_spans"] == "v002"
    assert default_prompt_version("context_filter_spans") == "v002"


def test_list_context_filter_spans_prompt_versions_includes_v002() -> None:
    versions = list_prompt_versions("context_filter_spans")
    assert "v001" in versions
    assert "v002" in versions


def test_default_context_classify_clusters_prompt_version_is_v002() -> None:
    assert DEFAULT_PROMPT_VERSIONS["context_classify_clusters"] == "v002"
    assert default_prompt_version("context_classify_clusters") == "v002"


def test_list_context_classify_clusters_prompt_versions_includes_v002() -> None:
    versions = list_prompt_versions("context_classify_clusters")
    assert "v001" in versions
    assert "v002" in versions


def test_list_classification_prompt_versions_includes_v004() -> None:
    versions = list_prompt_versions("classification")
    assert "v003" in versions
    assert "v004" in versions


def test_default_context_triage_prompt_version_is_v001() -> None:
    assert DEFAULT_PROMPT_VERSIONS["context_triage"] == "v001"
    assert default_prompt_version("context_triage") == "v001"


def test_list_context_triage_prompt_versions_only_v001() -> None:
    versions = list_prompt_versions("context_triage")
    assert versions == ["v001"]
