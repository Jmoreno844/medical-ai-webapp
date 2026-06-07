from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = PROJECT_ROOT / "document_generation_worker"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from evals.document_generation.lib import (  # noqa: E402
    EVALS_ROOT,
    EvalCase,
    evaluate_judge_expectations,
    load_clinical_template,
    load_judge_ground_truth,
)
from evals.document_generation.run_eval import (  # noqa: E402
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_PROMPT_VERSION,
    DEFAULT_JUDGE_PROVIDER,
    _env_or_default,
    judge_document,
)


DEFAULT_GROUND_TRUTH_PATH = EVALS_ROOT / "judge_ground_truth.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the LLM judge against ground-truth cases with known planted "
            "defects. Run this whenever the judge prompt or judge model changes."
        )
    )
    parser.add_argument("--ground-truth", default=str(DEFAULT_GROUND_TRUTH_PATH))
    parser.add_argument(
        "--judge-provider",
        default=_env_or_default("JUDGE_PROVIDER", DEFAULT_JUDGE_PROVIDER),
    )
    parser.add_argument(
        "--judge-model",
        default=_env_or_default("JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    )
    parser.add_argument(
        "--judge-prompt-version",
        default=_env_or_default("JUDGE_PROMPT_VERSION", DEFAULT_JUDGE_PROMPT_VERSION),
    )
    return parser.parse_args()


async def run() -> int:
    load_dotenv(WORKER_ROOT / ".env.local", override=False)
    load_dotenv(EVALS_ROOT / ".env.local", override=True)
    args = parse_args()

    cases = load_judge_ground_truth(Path(args.ground_truth))
    print(
        f"Validating judge {args.judge_provider}:{args.judge_model} "
        f"({args.judge_prompt_version}) against {len(cases)} ground-truth cases"
    )

    failed_cases = 0
    for case in cases:
        eval_case = EvalCase(
            id=case.id,
            template=load_clinical_template(case.template_file),
            context=case.context,
            transcription=case.transcription,
        )
        judge_result, _ = await judge_document(
            case=eval_case,
            generated_document=case.generated_document,
            judge_provider=args.judge_provider,
            judge_model=args.judge_model,
            judge_prompt_version=args.judge_prompt_version,
        )
        checks = evaluate_judge_expectations(judge_result, case.expectation)
        case_failed = any(not check.passed for check in checks)
        if case_failed:
            failed_cases += 1

        print(f"\n[{'FAIL' if case_failed else 'PASS'}] {case.id}")
        print(
            "    judge: "
            f"safety={judge_result.clinical_safety_score} "
            f"faithfulness={judge_result.faithfulness_score} "
            f"verdict={judge_result.verdict}"
        )
        for finding in judge_result.invented_info:
            print(f"      invented [{finding.severity}] {finding.item}")
        for finding in judge_result.contradiction_info:
            print(f"      contradiction [{finding.severity}] {finding.item}")
        for finding in judge_result.dosing_error_info:
            print(f"      dosing_error [{finding.severity}] {finding.item}")
        for finding in judge_result.missing_info:
            print(f"      missing [{finding.severity}/{finding.kind}] {finding.item}")
        for check in checks:
            print(f"    [{'ok' if check.passed else 'XX'}] {check.name}: {check.detail}")

    passed_cases = len(cases) - failed_cases
    print(f"\n{passed_cases}/{len(cases)} ground-truth cases passed")
    return 1 if failed_cases else 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
