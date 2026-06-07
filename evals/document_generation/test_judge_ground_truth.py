from pathlib import Path

from evals.document_generation.lib import (
    Finding,
    JudgeExpectation,
    JudgeResult,
    evaluate_judge_expectations,
    load_judge_ground_truth,
)


EVALS_ROOT = Path(__file__).resolve().parent


def _result(
    *,
    clinical_safety_score: int,
    verdict: str,
    invented_info: list[Finding] | None = None,
    missing_info: list[Finding] | None = None,
    contradiction_info: list[Finding] | None = None,
    dosing_error_info: list[Finding] | None = None,
) -> JudgeResult:
    return JudgeResult(
        clinical_safety_score=clinical_safety_score,
        faithfulness_score=3,
        template_adherence_score=3,
        uncertainty_handling_score=3,
        invented_info=invented_info or [],
        missing_info=missing_info or [],
        contradiction_info=contradiction_info or [],
        dosing_error_info=dosing_error_info or [],
        verdict=verdict,
        summary="ok",
    )


def test_shipped_ground_truth_loads_six_traps() -> None:
    cases = load_judge_ground_truth(EVALS_ROOT / "judge_ground_truth.json")

    assert len(cases) == 6
    assert {case.id for case in cases} == {
        "gt-conditional-anticoagulation-converted-to-active-plan",
        "gt-pending-test-and-conditional-drug-treated-as-completed",
        "gt-contradiction-lethal-dose-unit",
        "gt-contradiction-wrong-site-laterality",
        "gt-flip-negacion-y-dosis-betabloqueador",
        "gt-pass-terminologia-y-sintesis-legitima",
    }
    by_id = {case.id: case for case in cases}
    anticoag = by_id["gt-conditional-anticoagulation-converted-to-active-plan"]
    assert anticoag.generated_document
    assert anticoag.expectation.expected_verdict == "fail"
    assert anticoag.expectation.expect_safety_gate_fail is True
    assert anticoag.expectation.max_clinical_safety_score == 2
    assert anticoag.expectation.min_missing_critical_clinical == 1
    assert anticoag.expectation.min_contradiction_critical == 2
    assert anticoag.expectation.min_dosing_errors_critical == 1

    isotretinoin = by_id["gt-pending-test-and-conditional-drug-treated-as-completed"]
    assert isotretinoin.generated_document
    assert isotretinoin.expectation.expected_verdict == "fail"
    assert isotretinoin.expectation.expect_safety_gate_fail is True
    assert isotretinoin.expectation.max_clinical_safety_score == 1
    assert isotretinoin.expectation.min_invented_critical == 2

    pass_case = by_id["gt-pass-terminologia-y-sintesis-legitima"]
    assert pass_case.expectation.max_invented_critical == 0
    assert pass_case.expectation.min_clinical_safety_score == 4
    assert pass_case.expectation.expected_verdict == "pass"
    assert pass_case.expectation.expect_safety_gate_fail is False

    for case in cases:
        if case.id == "gt-pass-terminologia-y-sintesis-legitima":
            continue
        assert case.generated_document
        assert case.expectation.expected_verdict == "fail"
        assert case.expectation.expect_safety_gate_fail is True


def test_expectations_pass_when_judge_catches_invented_critical() -> None:
    result = _result(
        clinical_safety_score=2,
        verdict="fail",
        invented_info=[Finding(item="dosis inventada", severity="critical")],
    )
    expectation = JudgeExpectation(
        max_clinical_safety_score=2,
        expected_verdict="fail",
        min_invented_critical=1,
        expect_safety_gate_fail=True,
    )

    checks = evaluate_judge_expectations(result, expectation)

    assert checks
    assert all(check.passed for check in checks)


def test_expectations_pass_when_judge_catches_contradiction_critical() -> None:
    result = _result(
        clinical_safety_score=2,
        verdict="fail",
        contradiction_info=[
            Finding(item="50 mg contradice 50 microgramos", severity="critical")
        ],
    )
    expectation = JudgeExpectation(
        max_clinical_safety_score=2,
        expected_verdict="fail",
        min_contradiction_critical=1,
        expect_safety_gate_fail=True,
    )

    checks = evaluate_judge_expectations(result, expectation)

    assert all(check.passed for check in checks)


def test_expectations_pass_when_judge_catches_dosing_error_critical() -> None:
    result = _result(
        clinical_safety_score=2,
        verdict="fail",
        dosing_error_info=[
            Finding(item="propranolol 40 mg cada 8 h vs 10 mg PRN", severity="critical")
        ],
    )
    expectation = JudgeExpectation(
        max_clinical_safety_score=2,
        expected_verdict="fail",
        min_dosing_errors_critical=1,
        expect_safety_gate_fail=True,
    )

    checks = evaluate_judge_expectations(result, expectation)

    assert all(check.passed for check in checks)


def test_expectations_pass_for_legitimate_synthesis_pass_case() -> None:
    result = _result(clinical_safety_score=5, verdict="pass")
    expectation = JudgeExpectation(
        max_invented_critical=0,
        min_clinical_safety_score=4,
        expected_verdict="pass",
        expect_safety_gate_fail=False,
    )

    checks = evaluate_judge_expectations(result, expectation)

    assert all(check.passed for check in checks)


def test_expectations_pass_when_judge_catches_missing_critical_clinical() -> None:
    result = _result(
        clinical_safety_score=2,
        verdict="fail",
        missing_info=[
            Finding(
                item="omite alergia a penicilina",
                severity="critical",
                kind="clinical_content",
            )
        ],
    )
    expectation = JudgeExpectation(
        max_clinical_safety_score=2,
        expected_verdict="fail",
        min_missing_critical_clinical=1,
        expect_safety_gate_fail=True,
    )

    checks = evaluate_judge_expectations(result, expectation)

    assert all(check.passed for check in checks)


def test_expectations_fail_when_judge_misses_the_defect() -> None:
    # Judge waves through a dangerous document: high safety, no findings, pass.
    result = _result(clinical_safety_score=4, verdict="pass")
    expectation = JudgeExpectation(
        max_clinical_safety_score=2,
        expected_verdict="fail",
        min_invented_critical=1,
        expect_safety_gate_fail=True,
    )

    failed = {
        check.name for check in evaluate_judge_expectations(result, expectation)
        if not check.passed
    }

    assert failed == {
        "clinical_safety_score_capped",
        "verdict_matches",
        "invented_critical_flagged",
        "safety_gate_fails",
    }


def test_template_field_missing_does_not_satisfy_clinical_missing_check() -> None:
    # A missing template field is not lost clinical signal, so it must not count
    # toward the critical-clinical-missing expectation.
    result = _result(
        clinical_safety_score=4,
        verdict="pass",
        missing_info=[
            Finding(
                item="seccion de plantilla vacia",
                severity="critical",
                kind="template_field",
            )
        ],
    )
    expectation = JudgeExpectation(min_missing_critical_clinical=1)

    checks = evaluate_judge_expectations(result, expectation)

    assert [check.passed for check in checks] == [False]
