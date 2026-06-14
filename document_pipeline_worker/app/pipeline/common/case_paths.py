from __future__ import annotations

from pathlib import Path

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = AI_PIPELINE_ROOT / "cases"
TRANSCRIPT_CASES_INDEX = CASES_DIR / "index.json"
CLUSTER_CASES_DIR = CASES_DIR / "cluster"
CLUSTER_CASES_INDEX = CLUSTER_CASES_DIR / "index.json"
CONTEXT_CASES_DIR = CASES_DIR / "context"
CONTEXT_CASES_INDEX = CONTEXT_CASES_DIR / "index.json"

__all__ = [
    "AI_PIPELINE_ROOT",
    "CASES_DIR",
    "CLUSTER_CASES_DIR",
    "CLUSTER_CASES_INDEX",
    "CONTEXT_CASES_DIR",
    "CONTEXT_CASES_INDEX",
    "TRANSCRIPT_CASES_INDEX",
]
