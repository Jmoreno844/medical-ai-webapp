from __future__ import annotations

from pathlib import Path

from document_pipeline_core.common.pipeline_steps import get_step_spec
from document_pipeline_core.package_root import PACKAGE_ROOT

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = AI_PIPELINE_ROOT / "cases"
TRANSCRIPT_CASES_INDEX = CASES_DIR / "index.json"
CLUSTER_CASES_DIR = CASES_DIR / "cluster"
CLUSTER_CASES_INDEX = CLUSTER_CASES_DIR / "index.json"
CONTEXT_CASES_DIR = CASES_DIR / "context"
CONTEXT_CASES_INDEX = CONTEXT_CASES_DIR / "index.json"
E2E_RUNS_DIR = AI_PIPELINE_ROOT / "e2e_runs"
E2E_FAILED_RESULTS_DIR = E2E_RUNS_DIR / "failed_steps"


def harness_results_dir(step: str) -> Path:
    spec = get_step_spec(step)
    return AI_PIPELINE_ROOT / spec.results_dir.relative_to(PACKAGE_ROOT)


__all__ = [
    "AI_PIPELINE_ROOT",
    "CASES_DIR",
    "CLUSTER_CASES_DIR",
    "CLUSTER_CASES_INDEX",
    "CONTEXT_CASES_DIR",
    "CONTEXT_CASES_INDEX",
    "E2E_FAILED_RESULTS_DIR",
    "E2E_RUNS_DIR",
    "TRANSCRIPT_CASES_INDEX",
    "harness_results_dir",
]
