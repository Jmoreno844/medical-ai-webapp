from __future__ import annotations

import json
import sys


def _result(pass_value: bool, reason: str) -> None:
    print(
        json.dumps(
            {
                "pass": pass_value,
                "score": 1.0 if pass_value else 0.0,
                "reason": reason,
            }
        )
    )


output = json.loads(sys.argv[1])
context = json.loads(sys.argv[2])
vars_payload = context.get("vars") or {}
expected_sections = [
    str(section).strip().lower() for section in (vars_payload.get("expected_sections") or [])
]

if output.get("error"):
    _result(False, f"provider error: {output['error']}")
    raise SystemExit(0)

runtime_validation_error = output.get("runtime_validation_error")
sections = [str(section).strip().lower() for section in (output.get("sections") or []) if section]
covered_sections = set(sections)
missing_sections = [section for section in expected_sections if section not in covered_sections]

if runtime_validation_error:
    _result(False, runtime_validation_error)
elif missing_sections:
    _result(False, "missing required sections: " + ", ".join(missing_sections))
elif not sections:
    _result(False, "drafter returned zero sections")
else:
    _result(True, "drafter covered every required section")