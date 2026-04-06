from evals.shared.clinical_cases import all_live_clinical_cases


def test_live_eval_case_matrix_is_stable() -> None:
    cases = all_live_clinical_cases()

    # The multi-provider Promptfoo matrix is intentionally capped at 15 hard cases
    # for the first comparison round so developers can run it locally without the
    # suite becoming too slow or too expensive.
    assert len(cases) == 15
    assert len({case.slug for case in cases}) == len(cases)
    assert {case.edit_scope for case in cases} == {"propagation", "reinterpretation"}
    assert all(len(case.affected_sections) >= 3 for case in cases)