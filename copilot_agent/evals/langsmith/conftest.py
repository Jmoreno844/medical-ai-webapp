from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def live_langchain_planner():
    from evals.shared.live_eval_support import (
        build_live_planner_from_env,
        missing_live_eval_env,
    )

    missing = missing_live_eval_env()
    if missing:
        pytest.skip(
            "Missing environment for live copilot evals: " + ", ".join(missing)
        )
    return build_live_planner_from_env()


@pytest.fixture(scope="session")
def langsmith_experiment_metadata() -> dict[str, str]:
    return {
        "component": "copilot_agent",
        "eval_surface": "langsmith_pytest",
        "environment": os.environ.get("COPILOT_AGENT_ENV", "local"),
        "vertex_model": os.environ.get("VERTEX_MODEL", "gemini-2.5-flash"),
    }