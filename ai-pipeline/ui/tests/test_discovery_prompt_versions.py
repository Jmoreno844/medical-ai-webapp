from __future__ import annotations

from ui.discovery import (
    DEFAULT_PROMPT_VERSIONS,
    default_generation_prompt_version,
    default_harness_prompt_version,
    default_prompt_version,
    list_generation_prompt_versions,
    list_harness_prompt_versions,
    list_prompt_versions,
)


def test_default_classification_prompt_version_is_v004() -> None:
    assert DEFAULT_PROMPT_VERSIONS["classification"] == "v004"
    assert default_prompt_version("classification") == "v004"


def test_default_filtering_prompt_version_is_v002() -> None:
    assert DEFAULT_PROMPT_VERSIONS["filtering"] == "v002"
    assert default_prompt_version("filtering") == "v002"


def test_list_filtering_prompt_versions_includes_v002() -> None:
    versions = list_prompt_versions("filtering")
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


def test_list_classification_prompt_versions_only_v004() -> None:
    versions = list_harness_prompt_versions("classification")
    assert versions == ["v004"]


def test_list_clustering_harness_prompt_versions_only_v002() -> None:
    versions = list_harness_prompt_versions("clustering")
    assert versions == ["v002"]


def test_list_filtering_harness_prompt_versions_only_v002() -> None:
    versions = list_harness_prompt_versions("filtering")
    assert versions == ["v002"]


def test_default_harness_prompt_version_matches_step_default() -> None:
    assert default_harness_prompt_version("classification") == "v004"
    assert default_harness_prompt_version("clustering") == "v002"
    assert default_harness_prompt_version("filtering") == "v002"


def test_default_context_triage_prompt_version_is_v001() -> None:
    assert DEFAULT_PROMPT_VERSIONS["context_triage"] == "v001"
    assert default_prompt_version("context_triage") == "v001"


def test_list_context_triage_prompt_versions_only_v001() -> None:
    versions = list_prompt_versions("context_triage")
    assert versions == ["v001"]


def test_list_generation_prompt_versions_direct_excludes_v002_alias() -> None:
    versions = list_generation_prompt_versions(generation_route="direct")
    assert versions == ["v001"]


def test_list_generation_prompt_versions_two_step_uses_planner_renderer() -> None:
    versions = list_generation_prompt_versions(generation_route="two_step")
    assert versions == ["v001"]


def test_list_generation_prompt_versions_cluster_planner_uses_shared_version() -> None:
    versions = list_generation_prompt_versions(generation_route="cluster_planner")
    assert versions == ["v001"]


def test_list_generation_prompt_versions_direct_with_evidence() -> None:
    versions = list_generation_prompt_versions(generation_route="direct_with_evidence")
    assert versions == ["v001"]


def test_list_generation_prompt_versions_hybrid_uses_intersection() -> None:
    versions = list_generation_prompt_versions(generation_route="hybrid")
    assert versions == ["v001"]


def test_default_generation_prompt_version_matches_route() -> None:
    assert default_generation_prompt_version(generation_route="direct") == "v001"
    assert default_generation_prompt_version(generation_route="two_step") == "v001"
    assert default_generation_prompt_version(generation_route="cluster_planner") == "v001"
    assert default_generation_prompt_version(generation_route="direct_with_evidence") == "v001"
    assert default_generation_prompt_version(generation_route="hybrid") == "v001"
