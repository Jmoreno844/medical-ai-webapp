from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import evals.document_generation.lib as eval_lib  # noqa: E402

from evals.document_generation.lib import (  # noqa: E402
    EvalCase,
    load_cases,
    load_judge_prompt,
    load_prompt_version,
    parse_judge_response,
    parse_model_specs,
    render_generation_prompt,
    select_cases,
)
from evals.document_generation.run_eval import _stream_with_anthropic_api  # noqa: E402
from app.settings import Settings  # noqa: E402


def test_load_cases_reads_shared_cases_dataset() -> None:
    cases = load_cases(PROJECT_ROOT / "evals/document_generation/cases.json")

    assert len(cases) >= 3
    assert all(isinstance(case, EvalCase) for case in cases)
    assert cases[0].id
    assert "## Identificacion del documento" in cases[0].template


def test_render_generation_prompt_includes_case_content() -> None:
    prompt_template = load_prompt_version("document_generation_v001")
    case = EvalCase(
        id="demo",
        template="## Plan",
        context="Consulta de control",
        transcription="Paciente refiere mejoria",
    )

    rendered = render_generation_prompt(prompt_template, case)

    assert "## Plan" in rendered
    assert "Consulta de control" in rendered
    assert "Paciente refiere mejoria" in rendered


def test_load_cases_supports_template_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(eval_lib, "EVALS_ROOT", tmp_path)
    template_path = tmp_path / "shared-template.md"
    template_path.write_text("## Plan de manejo", encoding="utf-8")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        """
        [
          {
            "id": "demo",
            "template_file": "shared-template.md",
            "context": "Consulta de control",
            "transcription": "Paciente refiere mejoria"
          }
        ]
        """.strip(),
        encoding="utf-8",
    )

    cases = load_cases(cases_path)

    assert [case.template for case in cases] == ["## Plan de manejo"]


def test_load_judge_prompt_contains_expected_keys_instruction() -> None:
    judge_prompt = load_judge_prompt("clinical_document_judge_v001")

    assert "overall_score" in judge_prompt
    assert "clinical_safety_score" in judge_prompt
    assert "DOCUMENTO GENERADO" in judge_prompt


def test_parse_judge_response_accepts_json_inside_code_fence() -> None:
    raw = """```json
    {
      "overall_score": 4,
      "clinical_safety_score": 5,
      "faithfulness_score": 4,
      "template_adherence_score": 4,
      "uncertainty_handling_score": 5,
      "missing_or_invented_info": ["No encontro hallazgos inventados"],
      "verdict": "pass",
      "summary": "Documento prudente y util."
    }
    ```"""

    parsed = parse_judge_response(raw)

    assert parsed.overall_score == 4
    assert parsed.verdict == "pass"
    assert parsed.summary == "Documento prudente y util."


def test_parse_judge_response_rejects_non_json_output() -> None:
    with pytest.raises(ValueError, match="valid_json_object"):
        parse_judge_response("No puedo evaluarlo en este momento.")


def test_select_cases_supports_count_and_case_id() -> None:
    cases = load_cases(PROJECT_ROOT / "evals/document_generation/cases.json")

    selected = select_cases(cases, count=2)
    exact = select_cases(cases, case_id=cases[1].id)

    assert len(selected) == 2
    assert [case.id for case in exact] == [cases[1].id]


def test_parse_model_specs_maps_anthropic_alias_to_direct_api() -> None:
    specs = parse_model_specs("gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5@20251001")

    assert specs[0].provider == "google_genai"
    assert specs[1].provider == "anthropic_api"


@pytest.mark.asyncio
async def test_stream_with_anthropic_api_omits_top_p(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeStream:
        def __init__(self) -> None:
            self.text_stream = self._iter()

        async def _iter(self):
            yield "hola"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeMessages:
        def stream(self, **kwargs):
            captured.update(kwargs)
            return FakeStream()

    class FakeAnthropic:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.messages = FakeMessages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeAnthropic)

    settings = Settings(_env_file=None, ENVIRONMENT="test")
    chunks = []
    async for chunk in _stream_with_anthropic_api(
        prompt="ping",
        model="claude-haiku-4-5-20251001",
        settings=settings,
    ):
        chunks.append(chunk)

    assert chunks == ["hola"]
    assert captured["temperature"] == 0.4
    assert "top_p" not in captured
