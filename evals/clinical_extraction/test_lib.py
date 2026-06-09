from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.clinical_extraction.lib import (  # noqa: E402
    EVALS_ROOT,
    build_run_score_summaries,
    load_cases,
    load_extraction_prompt_log,
    normalize_extraction_prompt_version,
    parse_judge_response,
)


def test_extraction_prompt_version_defaults_to_v1_log() -> None:
    assert normalize_extraction_prompt_version("v1") == "v1"
    prompt = load_extraction_prompt_log("v1")
    assert "<objetivo>" in prompt
    assert "deferred_action" in prompt


def test_extraction_prompt_version_v0_log_exists() -> None:
    prompt = load_extraction_prompt_log("v0")
    assert "Reglas obligatorias" in prompt
    assert "ClinicalMentionsV2" in prompt


def test_load_cases_reads_transcript_and_reference_mentions() -> None:
    cases = load_cases(EVALS_ROOT / "cases.json")

    assert len(cases) >= 2
    assert cases[0].transcript_json["chunks"][0]["turns"][0]["speaker"] == "PACIENTE"
    assert "mentions" in cases[0].reference_mentions


def test_parse_judge_response_accepts_expected_shape() -> None:
    result = parse_judge_response(
        """
        {
          "faithfulness_score": 5,
          "atomicity_score": 4,
          "coding_score": 5,
          "grounding_score": 4,
          "invented_mentions": [],
          "missing_mentions": [{"item": "urocultivo pendiente", "severity": "major"}],
          "atomicity_issues": [],
          "coding_issues": [],
          "verdict": "pass",
          "summary": "Buena salida con una omision relevante."
        }
        """
    )

    assert result.verdict == "pass"
    assert result.missing_mentions[0].severity == "major"


def test_build_run_score_summaries_averages_dimensions() -> None:
    summaries = build_run_score_summaries(
        [
            {
                "case_id": "case-1",
                "outputs": [
                    {
                        "model_alias": "openai",
                        "provider": "openai",
                        "model": "gpt-5.4-mini",
                        "judge_result": {
                            "faithfulness_score": 5,
                            "atomicity_score": 4,
                            "coding_score": 5,
                            "grounding_score": 4,
                            "invented_mentions": [],
                            "missing_mentions": [],
                            "atomicity_issues": [],
                            "coding_issues": [],
                        },
                    }
                ],
            }
        ]
    )

    assert len(summaries) == 1
    assert summaries[0].overall_score == 4.5
