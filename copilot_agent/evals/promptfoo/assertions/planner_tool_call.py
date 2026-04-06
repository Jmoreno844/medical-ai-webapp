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

if output.get("error"):
    _result(False, f"provider error: {output['error']}")
    raise SystemExit(0)

tool_calls = output.get("tool_calls") or []
if len(tool_calls) != 1:
    _result(False, f"expected 1 tool call, got {len(tool_calls)}")
    raise SystemExit(0)

tool_call = tool_calls[0]
args = tool_call.get("args") or {}
invalid_args = sorted(set(args) - {"instruction", "target_document_id"})
instruction = str(args.get("instruction") or "").strip()
expected_document_id = vars_payload.get("expected_target_document_id")

if tool_call.get("name") != "propose_replace_span":
    _result(False, f"unexpected tool name: {tool_call.get('name')}")
elif invalid_args:
    _result(False, f"unexpected args: {', '.join(invalid_args)}")
elif args.get("target_document_id") != expected_document_id:
    _result(
        False,
        "target_document_id mismatch: "
        f"expected {expected_document_id}, got {args.get('target_document_id')}",
    )
elif not instruction:
    _result(False, "instruction was empty")
else:
    _result(True, "planner returned one schema-safe propose_replace_span call")