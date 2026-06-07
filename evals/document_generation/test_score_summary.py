from evals.document_generation.lib import (
    CaseFindings,
    Finding,
    build_run_score_summaries,
    estimate_generation_cost_usd,
)


def _judge_result(
    *,
    clinical_safety_score: int,
    faithfulness_score: int,
    template_adherence_score: int,
    uncertainty_handling_score: int,
    invented_info: list[dict[str, str]] | None = None,
    missing_info: list[dict[str, str]] | None = None,
    verdict: str = "pass",
) -> dict[str, object]:
    return {
        "clinical_safety_score": clinical_safety_score,
        "faithfulness_score": faithfulness_score,
        "template_adherence_score": template_adherence_score,
        "uncertainty_handling_score": uncertainty_handling_score,
        "invented_info": invented_info or [],
        "missing_info": missing_info or [],
        "contradiction_info": [],
        "dosing_error_info": [],
        "verdict": verdict,
        "summary": "ok",
    }


def _generation_metrics(
    *,
    time_to_first_token_ms: int,
    time_after_first_token_ms: int,
) -> dict[str, int]:
    return {
        "time_to_first_token_ms": time_to_first_token_ms,
        "time_after_first_token_ms": time_after_first_token_ms,
        "total_generation_ms": time_to_first_token_ms + time_after_first_token_ms,
    }


def _output(
    *,
    model_alias: str = "anthropic",
    provider: str = "anthropic_api",
    model: str = "claude-test",
    judge_result: dict[str, object],
    time_to_first_token_ms: int = 1000,
    time_after_first_token_ms: int = 2000,
) -> dict[str, object]:
    return {
        "model_alias": model_alias,
        "provider": provider,
        "model": model,
        "generation_metrics": _generation_metrics(
            time_to_first_token_ms=time_to_first_token_ms,
            time_after_first_token_ms=time_after_first_token_ms,
        ),
        "judge_result": judge_result,
    }


def _judge_output(
    *,
    judge_alias: str,
    judge_provider: str,
    judge_model: str,
    judge_result: dict[str, object],
) -> dict[str, object]:
    return {
        "judge_alias": judge_alias,
        "judge_provider": judge_provider,
        "judge_model": judge_model,
        "judge_result": judge_result,
        "judge_raw_response": "{}",
    }


def test_overall_score_uses_weighted_blend() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=4,
                        faithfulness_score=4,
                        template_adherence_score=4,
                        uncertainty_handling_score=4,
                    ),
                    time_to_first_token_ms=1000,
                    time_after_first_token_ms=2000,
                )
            ],
        },
        {
            "case_id": "case-b",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=4,
                        faithfulness_score=4,
                        template_adherence_score=4,
                        uncertainty_handling_score=3,
                    ),
                    time_to_first_token_ms=3000,
                    time_after_first_token_ms=4000,
                )
            ],
        },
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.evaluated_output_count == 2
    assert summary.dimension_averages["uncertainty_handling_score"] == 3.5
    # No findings, so effective == raw on every dimension.
    assert summary.effective_dimension_averages == summary.dimension_averages
    # case-a weighted = 4.0; case-b weighted = .4*4+.3*4+.2*3+.1*4 = 3.8
    assert summary.overall_score == 3.9
    assert summary.effective_dimension_averages["clinical_safety_score"] == 4.0
    assert summary.safety_gate_failures == 0
    assert summary.critical_invented_count == 0
    assert summary.overall_time_to_first_token_ms == 2000
    assert summary.overall_time_after_first_token_ms == 3000


def test_run_score_summaries_split_results_by_judge() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                {
                    "model_alias": "openai",
                    "provider": "openai_api",
                    "model": "gpt-5.4-mini",
                    "generation_metrics": _generation_metrics(
                        time_to_first_token_ms=1000,
                        time_after_first_token_ms=2000,
                    ),
                    "judge_outputs": [
                        _judge_output(
                            judge_alias="openai",
                            judge_provider="openai",
                            judge_model="gpt-5.4",
                            judge_result=_judge_result(
                                clinical_safety_score=5,
                                faithfulness_score=5,
                                template_adherence_score=5,
                                uncertainty_handling_score=5,
                            ),
                        ),
                        _judge_output(
                            judge_alias="anthropic",
                            judge_provider="anthropic",
                            judge_model="claude-opus-4-8",
                            judge_result=_judge_result(
                                clinical_safety_score=4,
                                faithfulness_score=4,
                                template_adherence_score=4,
                                uncertainty_handling_score=4,
                            ),
                        ),
                    ],
                }
            ],
        }
    ]

    summaries = build_run_score_summaries(case_results)

    assert len(summaries) == 2
    by_judge = {
        (summary.judge_alias, summary.judge_model): summary for summary in summaries
    }
    assert by_judge[("openai", "gpt-5.4")].overall_score == 5.0
    assert by_judge[("anthropic", "claude-opus-4-8")].overall_score == 4.0


def test_critical_invented_finding_hard_caps_safety_and_overall() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=5,
                        faithfulness_score=5,
                        template_adherence_score=5,
                        uncertainty_handling_score=5,
                        invented_info=[
                            {"item": "dosis de enalapril inventada", "severity": "critical"}
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    # Judge raw safety is preserved in dimension_averages, but the effective
    # safety is pinned to 1, faithfulness floored to 2, and overall gated to 1.
    assert summary.dimension_averages["clinical_safety_score"] == 5.0
    assert summary.effective_dimension_averages["clinical_safety_score"] == 1.0
    assert summary.effective_dimension_averages["faithfulness_score"] == 2.0
    assert summary.overall_score == 1.0
    assert summary.safety_gate_failures == 1
    assert summary.critical_invented_count == 1


def test_low_safety_without_critical_still_trips_gate() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=2,
                        faithfulness_score=5,
                        template_adherence_score=5,
                        uncertainty_handling_score=5,
                        missing_info=[
                            {
                                "item": "omite antecedente",
                                "severity": "major",
                                "kind": "clinical_content",
                            }
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.effective_dimension_averages["clinical_safety_score"] == 2.0
    assert summary.overall_score == 2.0
    assert summary.safety_gate_failures == 1
    assert summary.critical_invented_count == 0
    assert summary.critical_missing_count == 0


def test_critical_clinical_missing_hard_caps_safety() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=5,
                        faithfulness_score=4,
                        template_adherence_score=5,
                        uncertainty_handling_score=5,
                        missing_info=[
                            {
                                "item": "omite alergia a penicilina conocida",
                                "severity": "critical",
                                "kind": "clinical_content",
                            }
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.dimension_averages["clinical_safety_score"] == 5.0
    assert summary.effective_dimension_averages["clinical_safety_score"] == 1.0
    assert summary.effective_dimension_averages["faithfulness_score"] == 2.0
    assert summary.overall_score == 1.0
    assert summary.safety_gate_failures == 1
    assert summary.critical_missing_count == 1
    assert summary.critical_invented_count == 0


def test_critical_template_missing_does_not_cap_safety() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=4,
                        faithfulness_score=4,
                        template_adherence_score=4,
                        uncertainty_handling_score=4,
                        missing_info=[
                            {
                                "item": "seccion de plantilla vacia",
                                "severity": "critical",
                                "kind": "template_field",
                            }
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    # A template-field gap, even tagged critical, is not lost clinical signal:
    # it floors template adherence (4 -> 2) but must not touch the safety floor.
    assert summary.effective_dimension_averages["clinical_safety_score"] == 4.0
    assert summary.effective_dimension_averages["template_adherence_score"] == 2.0
    # weighted = .4*4 + .3*4 + .2*4 + .1*2 = 3.8
    assert summary.overall_score == 3.8
    assert summary.safety_gate_failures == 0
    assert summary.critical_missing_count == 0


def test_major_invented_finding_floors_safety_and_faithfulness() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=4,
                        faithfulness_score=4,
                        template_adherence_score=4,
                        uncertainty_handling_score=4,
                        invented_info=[{"item": "exceso de certeza", "severity": "major"}],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    # Consistency floor: a major invention cannot leave safety/faithfulness at 4;
    # the rubric caps both at 3 (this is the leniency the judge alone leaked).
    assert summary.dimension_averages["clinical_safety_score"] == 4.0
    assert summary.effective_dimension_averages["clinical_safety_score"] == 3.0
    assert summary.effective_dimension_averages["faithfulness_score"] == 3.0
    assert summary.effective_dimension_averages["template_adherence_score"] == 4.0
    # weighted = .4*3 + .3*3 + .2*4 + .1*4 = 3.3 (safety 3 does not trip the gate)
    assert summary.overall_score == 3.3
    assert summary.safety_gate_failures == 0
    assert summary.critical_invented_count == 0


def test_multiple_minor_template_fields_floor_template_adherence() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=5,
                        faithfulness_score=5,
                        template_adherence_score=4,
                        uncertainty_handling_score=5,
                        missing_info=[
                            {
                                "item": "confiabilidad no documentada",
                                "severity": "minor",
                                "kind": "template_field",
                            },
                            {
                                "item": "servicio ubicado fuera del campo esperado",
                                "severity": "minor",
                                "kind": "template_field",
                            },
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.dimension_averages["template_adherence_score"] == 4.0
    assert summary.effective_dimension_averages["template_adherence_score"] == 3.0
    assert summary.effective_dimension_averages["clinical_safety_score"] == 5.0
    assert summary.overall_score == 4.8


def test_two_major_inventions_pull_overall_down_real_case() -> None:
    # Regression for the disnea case: the judge gave safety 4 / faith 4 with two
    # major inventions listed, which the rubric says must cap both at 3.
    case_results = [
        {
            "case_id": "consulta-externa-disnea-contexto-valido",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=4,
                        faithfulness_score=4,
                        template_adherence_score=5,
                        uncertainty_handling_score=4,
                        invented_info=[
                            {"item": "febricula registrada en consulta", "severity": "major"},
                            {"item": "estabilidad limitrofe", "severity": "major"},
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.effective_dimension_averages["clinical_safety_score"] == 3.0
    assert summary.effective_dimension_averages["faithfulness_score"] == 3.0
    # weighted = .4*3 + .3*3 + .2*4 + .1*5 = 3.4 (was 4.1 before the floor)
    assert summary.overall_score == 3.4


def test_findings_grouped_by_case() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    judge_result=_judge_result(
                        clinical_safety_score=4,
                        faithfulness_score=4,
                        template_adherence_score=4,
                        uncertainty_handling_score=4,
                        invented_info=[{"item": "plan no afirmado", "severity": "major"}],
                        missing_info=[
                            {
                                "item": "omite control previo",
                                "severity": "minor",
                                "kind": "template_field",
                            }
                        ],
                    )
                )
            ],
        }
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.findings_by_case == (
        CaseFindings(
            case_id="case-a",
            invented_info=(Finding(item="plan no afirmado", severity="major"),),
            missing_info=(
                Finding(
                    item="omite control previo",
                    severity="minor",
                    kind="template_field",
                ),
            ),
            contradiction_info=(),
            dosing_error_info=(),
        ),
    )
    assert summary.to_dict()["findings_by_case"] == [
        {
            "case_id": "case-a",
            "invented_info": [{"item": "plan no afirmado", "severity": "major"}],
            "missing_info": [
                {
                    "item": "omite control previo",
                    "severity": "minor",
                    "kind": "template_field",
                }
            ],
            "contradiction_info": [],
            "dosing_error_info": [],
        }
    ]


def test_build_run_score_summaries_groups_by_model() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                _output(
                    model_alias="anthropic",
                    provider="anthropic_api",
                    model="claude-a",
                    judge_result=_judge_result(
                        clinical_safety_score=5,
                        faithfulness_score=5,
                        template_adherence_score=5,
                        uncertainty_handling_score=5,
                    ),
                    time_to_first_token_ms=500,
                    time_after_first_token_ms=1500,
                ),
                _output(
                    model_alias="gemini",
                    provider="google_vertex",
                    model="gemini-test",
                    judge_result=_judge_result(
                        clinical_safety_score=3,
                        faithfulness_score=3,
                        template_adherence_score=3,
                        uncertainty_handling_score=3,
                    ),
                    time_to_first_token_ms=900,
                    time_after_first_token_ms=1100,
                ),
            ],
        }
    ]

    summaries = build_run_score_summaries(case_results)

    assert len(summaries) == 2
    by_model = {summary.model: summary.overall_score for summary in summaries}
    assert by_model["claude-a"] == 5.0
    assert by_model["gemini-test"] == 3.0


def test_estimate_generation_cost_usd_for_gpt_5_4_mini() -> None:
    total_cost, breakdown = estimate_generation_cost_usd(
        model="gpt-5.4-mini",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        thinking_tokens=1_000_000,
    )

    assert total_cost == 9.75
    assert breakdown["input_usd_per_million"] == 0.75
    assert breakdown["output_usd_per_million"] == 4.5
    assert breakdown["input_cost_usd"] == 0.75
    assert breakdown["thinking_cost_usd"] == 4.5
    assert breakdown["visible_output_cost_usd"] == 4.5


def test_run_score_summary_aggregates_generation_token_metrics() -> None:
    case_results = [
        {
            "case_id": "case-a",
            "outputs": [
                {
                    "model_alias": "openai",
                    "provider": "openai_api",
                    "model": "gpt-5.4-mini",
                    "generation_metrics": {
                        "time_to_first_token_ms": 1000,
                        "time_after_first_token_ms": 2000,
                        "total_generation_ms": 3000,
                        "input_tokens": 100,
                        "output_tokens": 200,
                        "thinking_tokens": 50,
                        "estimated_cost_usd": 0.001,
                    },
                    "judge_result": _judge_result(
                        clinical_safety_score=5,
                        faithfulness_score=5,
                        template_adherence_score=5,
                        uncertainty_handling_score=5,
                    ),
                }
            ],
        },
        {
            "case_id": "case-b",
            "outputs": [
                {
                    "model_alias": "openai",
                    "provider": "openai_api",
                    "model": "gpt-5.4-mini",
                    "generation_metrics": {
                        "time_to_first_token_ms": 1100,
                        "time_after_first_token_ms": 2100,
                        "total_generation_ms": 3200,
                        "input_tokens": 120,
                        "output_tokens": 180,
                        "thinking_tokens": 20,
                        "estimated_cost_usd": 0.002,
                    },
                    "judge_result": _judge_result(
                        clinical_safety_score=5,
                        faithfulness_score=5,
                        template_adherence_score=5,
                        uncertainty_handling_score=5,
                    ),
                }
            ],
        },
    ]

    summary = build_run_score_summaries(case_results)[0]

    assert summary.total_input_tokens == 220
    assert summary.total_output_tokens == 380
    assert summary.total_thinking_tokens == 70
    assert summary.total_estimated_cost_usd == 0.003
    assert summary.token_metric_sample_count == 2
