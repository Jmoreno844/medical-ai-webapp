from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def create_tests() -> list[dict]:
    from evals.shared.clinical_cases import all_live_clinical_cases

    tests: list[dict] = []
    for case in all_live_clinical_cases():
        tests.append(
            {
                "description": f"planner contract :: {case.slug}",
                "vars": {
                    "mode": "planner_tool_call",
                    "case_slug": case.slug,
                    "user_message": case.user_message,
                    "expected_target_document_id": case.target_document_id,
                    "expected_sections": list(case.affected_sections),
                },
                "metadata": {
                    "feature": "planner",
                    "scope": case.edit_scope,
                    "difficulty": "hard",
                },
                "assert": [
                    {"type": "is-json"},
                    {
                        "type": "python",
                        "value": "file://assertions/planner_tool_call.py",
                        "metric": "planner_contract",
                    },
                ],
            }
        )
        tests.append(
            {
                "description": f"drafter coverage :: {case.slug}",
                "vars": {
                    "mode": "patch_drafter",
                    "case_slug": case.slug,
                    "user_message": case.user_message,
                    "expected_target_document_id": case.target_document_id,
                    "expected_sections": list(case.affected_sections),
                },
                "metadata": {
                    "feature": "drafter",
                    "scope": case.edit_scope,
                    "difficulty": "hard",
                },
                "assert": [
                    {"type": "is-json"},
                    {
                        "type": "python",
                        "value": "file://assertions/drafted_sections.py",
                        "metric": "drafted_sections",
                    },
                ],
            }
        )
    return tests