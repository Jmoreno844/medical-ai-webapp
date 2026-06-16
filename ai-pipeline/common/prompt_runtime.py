from __future__ import annotations

import re
from pathlib import Path

from common.pipeline_steps import get_step_spec
from common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_prompt_versions, py_system_prompt
from common.prompts import PROMPT_VERSION_PATTERN, load_prompt as load_prompt_from_file, normalize_prompt_version

_GENERATION_EXTRA_PY_STEPS = frozenset({"generation"})


def uses_py_prompt(step: str, version: str) -> bool:
    spec = get_step_spec(step)
    return is_py_prompt_version(spec.registry_step, version)


def structured_output_enabled(step: str, version: str) -> bool:
    spec = get_step_spec(step)
    return normalize_prompt_version(version) in spec.structured_output_versions


def load_system_prompt(step: str, version: str) -> str:
    spec = get_step_spec(step)
    normalized = normalize_prompt_version(version)
    if uses_py_prompt(step, normalized):
        return py_system_prompt(spec.registry_step, normalized)
    return load_prompt_from_file(
        prompts_dir=spec.prompts_dir,
        filename_stem=spec.prompt_stem,
        version=normalized,
    )


def prompt_file_path(step: str, version: str) -> Path:
    spec = get_step_spec(step)
    from common.prompts import prompt_file_path as resolve_prompt_file_path

    return resolve_prompt_file_path(
        prompts_dir=spec.prompts_dir,
        filename_stem=spec.prompt_stem,
        version=version,
    )


def prompt_reference(step: str, version: str) -> str:
    spec = get_step_spec(step)
    normalized = normalize_prompt_version(version)
    if uses_py_prompt(step, normalized):
        module_path = load_py_prompt_module(spec.registry_step, normalized).__name__
        return f"{module_path.replace('.', '/')}.py"
    return str(prompt_file_path(step, normalized).relative_to(spec.module_dir))


def build_output_schema(
    step: str,
    version: str,
    **kwargs: object,
) -> dict[str, object] | None:
    if not structured_output_enabled(step, version):
        return None
    spec = get_step_spec(step)
    module = load_py_prompt_module(spec.registry_step, version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(f"py_prompt_missing_output_schema: {step}:{version}")
    schema = output_schema_fn(**kwargs)
    if not isinstance(schema, dict):
        raise ValueError(f"py_prompt_invalid_output_schema: {step}:{version}")
    return schema


def list_prompt_versions(step: str) -> list[str]:
    spec = get_step_spec(step)
    prompts_dir = spec.prompts_dir
    stem = spec.prompt_stem
    txt_versions: set[str] = set()
    if prompts_dir.is_dir():
        txt_versions = {
            path.stem.removeprefix(f"{stem}_")
            for path in prompts_dir.glob(f"{stem}_v*.txt")
            if PROMPT_VERSION_PATTERN.fullmatch(path.stem.removeprefix(f"{stem}_"))
        }
    py_versions = set(py_prompt_versions(spec.registry_step))
    if step in _GENERATION_EXTRA_PY_STEPS:
        py_versions |= set(py_prompt_versions("generation_direct"))
    versions = sorted(txt_versions | py_versions)
    if versions:
        return versions
    return [spec.default_prompt_version]


def resolve_prompt_version(step: str, version: str | None = None) -> str:
    if version is not None and version.strip():
        normalized = normalize_prompt_version(version)
        available = list_prompt_versions(step)
        if normalized in available:
            return normalized
    preferred = get_step_spec(step).default_prompt_version
    available = list_prompt_versions(step)
    if preferred in available:
        return preferred
    return available[0]


__all__ = [
    "build_output_schema",
    "list_prompt_versions",
    "load_system_prompt",
    "prompt_file_path",
    "prompt_reference",
    "resolve_prompt_version",
    "structured_output_enabled",
    "uses_py_prompt",
]
