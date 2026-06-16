from __future__ import annotations

from pathlib import Path

# Distribution root: shared/document_pipeline_core/ (templates live here).
CORE_DIST_ROOT = Path(__file__).resolve().parents[1]
# Importable package root: shared/document_pipeline_core/document_pipeline_core/
PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_TEMPLATES_DIR = CORE_DIST_ROOT / "templates"

# Back-compat alias used by pipeline_steps module path resolution.
CORE_PACKAGE_ROOT = PACKAGE_ROOT

__all__ = [
    "CORE_DIST_ROOT",
    "CORE_PACKAGE_ROOT",
    "DEFAULT_TEMPLATES_DIR",
    "PACKAGE_ROOT",
]
