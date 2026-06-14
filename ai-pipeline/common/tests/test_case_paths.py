from __future__ import annotations

from common.case_paths import (
    CLUSTER_CASES_DIR,
    CLUSTER_CASES_INDEX,
    CONTEXT_CASES_DIR,
    CONTEXT_CASES_INDEX,
    TRANSCRIPT_CASES_INDEX,
)


def test_case_paths_layout() -> None:
    assert TRANSCRIPT_CASES_INDEX.name == "index.json"
    assert TRANSCRIPT_CASES_INDEX.parent.name == "cases"
    assert CLUSTER_CASES_INDEX == CLUSTER_CASES_DIR / "index.json"
    assert CONTEXT_CASES_INDEX == CONTEXT_CASES_DIR / "index.json"
    assert CLUSTER_CASES_INDEX.is_file()
    assert CONTEXT_CASES_INDEX.is_file()
    assert (CLUSTER_CASES_DIR / "case1" / "finca_animales_y_rasguno.json").is_file()
