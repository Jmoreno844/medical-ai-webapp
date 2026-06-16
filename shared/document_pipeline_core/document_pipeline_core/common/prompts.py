from __future__ import annotations

import re
from pathlib import Path

DEFAULT_PROMPT_VERSION = "v001"

PROMPT_VERSION_PATTERN = re.compile(r"^v\d{3}$")


def normalize_prompt_version(raw: str) -> str:
    normalized = raw.strip().lower()
    if PROMPT_VERSION_PATTERN.fullmatch(normalized):
        return normalized
    raise ValueError(
        f"ai_pipeline_prompt_version_invalid: {raw!r} "
        "(expected format vNNN, for example v001)"
    )


def prompt_file_path(*, prompts_dir: Path, filename_stem: str, version: str) -> Path:
    normalized = normalize_prompt_version(version)
    return prompts_dir / f"{filename_stem}_{normalized}.txt"


def load_prompt(*, prompts_dir: Path, filename_stem: str, version: str) -> str:
    path = prompt_file_path(
        prompts_dir=prompts_dir,
        filename_stem=filename_stem,
        version=version,
    )
    if not path.is_file():
        raise FileNotFoundError(f"ai_pipeline_prompt_not_found: {path}")
    return path.read_text(encoding="utf-8").strip()
