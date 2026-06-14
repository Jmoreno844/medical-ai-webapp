"""Expose ai-pipeline packages (common, filtering, ...) on sys.path for uvicorn."""

from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent / "pipeline"
_PIPELINE_ROOT_STR = str(_PIPELINE_ROOT)
if _PIPELINE_ROOT_STR not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT_STR)
