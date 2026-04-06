from evals.shared.clinical_reasoning_cases import all_clinical_reasoning_cases


def test_clinical_reasoning_case_matrix_is_stable() -> None:
    cases = all_clinical_reasoning_cases()

    assert len(cases) == 3
    assert len({case.slug for case in cases}) == len(cases)
    assert {case.level for case in cases} == {"medio", "dificil", "muy_dificil"}
