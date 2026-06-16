from __future__ import annotations

from document_pipeline_core.common.pipeline_steps import get_step_spec, list_registered_steps
from document_pipeline_core.package_root import PACKAGE_ROOT

from harness.paths import AI_PIPELINE_ROOT, harness_results_dir
from ui.discovery import (
    DEFAULT_PROMPT_VERSIONS,
    MODULE_DIRS,
    PROMPT_STEMS,
    default_prompt_version,
    list_prompt_versions,
)


def test_discovery_module_dirs_point_to_harness_mirror() -> None:
    spec = get_step_spec("filtering")
    assert MODULE_DIRS["filtering"] == AI_PIPELINE_ROOT / spec.module_dir.relative_to(
        PACKAGE_ROOT
    )


def test_discovery_prompt_versions_from_core_registry() -> None:
    assert default_prompt_version("filtering") == DEFAULT_PROMPT_VERSIONS["filtering"]
    versions = list_prompt_versions("filtering")
    assert versions
    assert DEFAULT_PROMPT_VERSIONS["filtering"] in versions


def test_harness_results_dir_under_ai_pipeline_root() -> None:
    results = harness_results_dir("filtering")
    assert results == AI_PIPELINE_ROOT / "filtering" / "results"


def test_registered_steps_include_context_substeps() -> None:
    steps = list_registered_steps()
    assert "context_triage" in steps
    assert "context_cluster_spans" in steps


def test_harness_case_paths_layout() -> None:
    from harness.paths import (
        CLUSTER_CASES_DIR,
        CLUSTER_CASES_INDEX,
        CONTEXT_CASES_DIR,
        CONTEXT_CASES_INDEX,
        TRANSCRIPT_CASES_INDEX,
    )

    assert TRANSCRIPT_CASES_INDEX.name == "index.json"
    assert TRANSCRIPT_CASES_INDEX.parent.name == "cases"
    assert CLUSTER_CASES_INDEX == CLUSTER_CASES_DIR / "index.json"
    assert CONTEXT_CASES_INDEX == CONTEXT_CASES_DIR / "index.json"
    assert CLUSTER_CASES_INDEX.is_file()
    assert CONTEXT_CASES_INDEX.is_file()
