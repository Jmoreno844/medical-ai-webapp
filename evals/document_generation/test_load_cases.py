import json
from pathlib import Path

import pytest

from evals.document_generation.lib import EvalCase, load_cases, resolve_template_file, select_cases
from evals.document_generation.run_eval import (
    _build_anthropic_judge_repair_message,
    parse_judge_specs,
)


TEMPLATE_PATH = "templates/clinical_document_template_v002.md"


def test_load_cases_applies_template_from_runner_argument(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-a",
                    "context": "contexto",
                    "transcription": "transcripcion",
                }
            ]
        ),
        encoding="utf-8",
    )

    cases = load_cases(cases_path, template_file=TEMPLATE_PATH)

    assert len(cases) == 1
    assert cases[0].template.startswith("(Reglas generales:")
    assert (
        resolve_template_file(TEMPLATE_PATH).name
        == "clinical_document_template_v002.md"
    )


def test_resolve_template_file_rejects_non_templates_path() -> None:
    with pytest.raises(ValueError, match="template_file_must_live_under_templates"):
        resolve_template_file("v2")


def test_load_cases_rejects_template_in_case_file(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-a",
                    "template_file": "templates/clinical_document_template_v001.md",
                    "context": "contexto",
                    "transcription": "transcripcion",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case_must_not_include_template"):
        load_cases(cases_path, template_file=TEMPLATE_PATH)


def test_parse_judge_specs_supports_multiple_judges() -> None:
    judges = parse_judge_specs(
        "openai:gpt-5.4,anthropic:claude-opus-4-8",
        default_provider="openai",
        default_model="gpt-5.4",
    )

    assert [(judge.alias, judge.provider, judge.model) for judge in judges] == [
        ("openai", "openai", "gpt-5.4"),
        ("anthropic", "anthropic", "claude-opus-4-8"),
    ]


def test_load_cases_preserves_structured_notes(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-a",
                    "context": "contexto",
                    "transcription": "transcripcion",
                    "notes": {
                        "pendientes": ["troponina", "d-dimero"],
                        "condicional": "solo si sale alterado",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    cases = load_cases(cases_path, template_file=TEMPLATE_PATH)

    assert cases[0].notes == {
        "pendientes": ["troponina", "d-dimero"],
        "condicional": "solo si sale alterado",
    }


def test_select_cases_supports_last_n() -> None:
    cases = [
        EvalCase("case-a", "template", "contexto", "transcripcion"),
        EvalCase("case-b", "template", "contexto", "transcripcion"),
        EvalCase("case-c", "template", "contexto", "transcripcion"),
    ]

    selected = select_cases(cases, last=2)

    assert [case.id for case in selected] == ["case-b", "case-c"]


def test_select_cases_rejects_count_and_last_together() -> None:
    cases = [EvalCase("case-a", "template", "contexto", "transcripcion")]

    with pytest.raises(ValueError, match="count_and_last_are_mutually_exclusive"):
        select_cases(cases, count=1, last=1)


def test_anthropic_repair_message_demands_full_schema() -> None:
    message = _build_anthropic_judge_repair_message(
        parse_error="judge_response_missing_fields: uncertainty_handling_score",
        previous_raw='{"clinical_safety_score": 4}',
    )

    assert "uncertainty_handling_score" in message
    assert "Devuelve de nuevo TODO el objeto JSON completo" in message
    assert '{"clinical_safety_score": 4}' in message
