from __future__ import annotations

from document_pipeline_core.common.pipeline_steps import (
    CONTEXT_PIPELINE_SUBSTEPS,
    default_context_substep_versions,
    default_prompt_version,
    get_step_spec,
)
from document_pipeline_core.common.prompt_runtime import list_prompt_versions


def test_registry_default_versions() -> None:
    assert default_prompt_version("filtering") == "v002"
    assert default_prompt_version("classification") == "v004"
    assert default_prompt_version("context_filter_spans") == "v002"


def test_context_substep_defaults() -> None:
    versions = default_context_substep_versions()
    assert versions["context_triage"] == "v001"
    assert versions["context_filter_spans"] == "v002"
    assert versions["context_section_adapter"] == "v003"
    assert tuple(versions) == CONTEXT_PIPELINE_SUBSTEPS


def test_get_step_spec_module_dirs_exist() -> None:
    for step in (
        "filtering",
        "context_triage",
        "context_document_directive_filter",
        "generation_direct",
    ):
        spec = get_step_spec(step)
        assert spec.module_dir.is_dir()


def test_list_prompt_versions_filtering_includes_v002() -> None:
    versions = list_prompt_versions("filtering")
    assert "v002" in versions


def test_prompt_reference_py_prompt_is_py_path() -> None:
    from document_pipeline_core.common.prompt_runtime import prompt_reference

    ref = prompt_reference("context_triage", "v001")
    assert ref.endswith(".py")
