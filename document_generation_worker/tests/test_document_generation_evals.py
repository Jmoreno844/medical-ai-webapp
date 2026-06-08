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
    JudgeResult,
    load_cases,
    load_judge_prompt,
    load_prompt_version,
    parse_judge_response,
    parse_model_specs,
    render_generation_prompt,
    select_cases,
)
from evals.document_generation.run_eval import (  # noqa: E402
    ANTHROPIC_EVAL_MAX_OUTPUT_TOKENS,
    GenerationConfig,
    _generate_with_anthropic_api,
    _generate_with_openai_chat_api,
    _generate_with_openai_responses_api,
)


def test_load_cases_reads_shared_cases_dataset() -> None:
    cases = load_cases(PROJECT_ROOT / "evals/document_generation/cases.json")

    assert len(cases) >= 3
    assert all(isinstance(case, EvalCase) for case in cases)
    assert cases[0].id
    assert "REGLAS DE LA PLANTILLA" in cases[0].template


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


def test_load_cases_applies_runner_template_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(eval_lib, "EVALS_ROOT", tmp_path)
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    template_path = templates_dir / "shared-template.md"
    template_path.write_text("## Plan de manejo", encoding="utf-8")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        """
        [
          {
            "id": "demo",
            "context": "Consulta de control",
            "transcription": "Paciente refiere mejoria"
          }
        ]
        """.strip(),
        encoding="utf-8",
    )

    cases = load_cases(cases_path, template_file="templates/shared-template.md")

    assert [case.template for case in cases] == ["## Plan de manejo"]


def test_load_cases_rejects_template_file_in_case_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(eval_lib, "EVALS_ROOT", tmp_path)
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

    with pytest.raises(ValueError, match="case_must_not_include_template"):
        load_cases(cases_path, template_file="shared-template.md")


def test_load_judge_prompt_contains_expected_keys_instruction() -> None:
    judge_prompt = load_judge_prompt("clinical_document_judge_v002")

    assert "clinical_safety_score" in judge_prompt
    assert "invented_info" in judge_prompt
    assert "missing_info" in judge_prompt
    assert "contradiction_info" in judge_prompt
    assert "dosing_error_info" in judge_prompt
    assert "DOCUMENTO GENERADO" in judge_prompt


def test_parse_judge_response_accepts_json_inside_code_fence() -> None:
    raw = """```json
    {
      "clinical_safety_score": 5,
      "faithfulness_score": 4,
      "template_adherence_score": 4,
      "uncertainty_handling_score": 5,
      "invented_info": [],
      "missing_info": [{"item": "omite control previo", "severity": "minor", "kind": "template_field"}],
      "contradiction_info": [],
      "dosing_error_info": [],
      "verdict": "pass",
      "summary": "Documento prudente y util."
    }
    ```"""

    parsed = parse_judge_response(raw)

    assert parsed.clinical_safety_score == 5
    assert parsed.invented_info == []
    assert parsed.missing_info[0].item == "omite control previo"
    assert parsed.missing_info[0].severity == "minor"
    assert parsed.missing_info[0].kind == "template_field"
    assert parsed.verdict == "pass"
    assert parsed.summary == "Documento prudente y util."


def test_parse_judge_response_requires_kind_on_missing_info() -> None:
    raw = """
    {
      "clinical_safety_score": 4,
      "faithfulness_score": 4,
      "template_adherence_score": 3,
      "uncertainty_handling_score": 4,
      "invented_info": [],
      "missing_info": [{"item": "omite antecedente", "severity": "major"}],
      "contradiction_info": [],
      "dosing_error_info": [],
      "verdict": "pass",
      "summary": "Falta tipo de omision."
    }
    """

    with pytest.raises(ValueError, match="missing_info_kind_must_be_one_of"):
        parse_judge_response(raw)


def test_parse_judge_response_rejects_non_json_output() -> None:
    with pytest.raises(ValueError, match="valid_json_object"):
        parse_judge_response("No puedo evaluarlo en este momento.")


def test_parse_judge_response_rejects_invalid_severity() -> None:
    raw = """
    {
      "clinical_safety_score": 2,
      "faithfulness_score": 3,
      "template_adherence_score": 4,
      "uncertainty_handling_score": 3,
      "invented_info": [{"item": "dosis inventada", "severity": "fatal"}],
      "missing_info": [],
      "contradiction_info": [],
      "dosing_error_info": [],
      "verdict": "fail",
      "summary": "Riesgo."
    }
    """

    with pytest.raises(ValueError, match="severity_must_be_one_of"):
        parse_judge_response(raw)


def test_select_cases_supports_count_and_case_id() -> None:
    cases = load_cases(PROJECT_ROOT / "evals/document_generation/cases.json")

    selected = select_cases(cases, count=2)
    exact = select_cases(cases, case_id=cases[1].id)

    assert len(selected) == 2
    assert [case.id for case in exact] == [cases[1].id]


def test_parse_model_specs_maps_anthropic_alias_to_direct_api() -> None:
    specs = parse_model_specs("gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5@20251001")

    assert specs[0].provider == "google_vertex"
    assert specs[1].provider == "anthropic_api"


def test_parse_model_specs_maps_openai_alias_to_direct_api() -> None:
    specs = parse_model_specs("openai:gpt-5.4-mini")

    assert len(specs) == 1
    assert specs[0].alias == "openai"
    assert specs[0].provider == "openai_api"
    assert specs[0].model == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_generate_with_openai_api_streams_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeDelta:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeChoice:
        def __init__(self, content: str) -> None:
            self.delta = FakeDelta(content)

    class FakeCompletionTokensDetails:
        reasoning_tokens = 12

    class FakeUsage:
        prompt_tokens = 100
        completion_tokens = 52
        completion_tokens_details = FakeCompletionTokensDetails()

    class FakeChunk:
        def __init__(self, *, content: str = "", usage: object | None = None) -> None:
            self.choices = [FakeChoice(content)] if content else []
            self.usage = usage

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)

            async def _iter():
                yield FakeChunk(content="hola")
                yield FakeChunk(content=" mundo")
                yield FakeChunk(usage=FakeUsage())

            return _iter()

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.chat = FakeChat()

    monkeypatch.setattr("openai.AsyncOpenAI", FakeOpenAI)

    generation_config = GenerationConfig(
        openai_reasoning_effort="none",
        anthropic_thinking_budget_tokens=None,
    )
    result = await _generate_with_openai_chat_api(
        prompt="ping",
        model="gpt-5.4-mini",
        generation_config=generation_config,
    )

    assert result.generated_document == "hola mundo"
    assert result.first_token_at is not None
    assert result.token_usage is not None
    assert result.token_usage.input_tokens == 100
    assert result.token_usage.thinking_tokens == 12
    assert result.token_usage.output_tokens == 40
    assert result.generation_reasoning is None
    assert captured["model"] == "gpt-5.4-mini"
    assert captured["temperature"] == 0.0
    assert captured["reasoning_effort"] == "none"
    assert "max_completion_tokens" not in captured
    assert captured["stream"] is True
    assert captured["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_generate_with_openai_responses_api_captures_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeOutputTokensDetails:
        reasoning_tokens = 25

    class FakeUsage:
        input_tokens = 100
        output_tokens = 45
        output_tokens_details = FakeOutputTokensDetails()

    class FakeResponse:
        usage = FakeUsage()

    class FakeCompletedEvent:
        type = "response.completed"
        response = FakeResponse()

    async def _fake_stream_events():
        yield type("Event", (), {"type": "response.reasoning_text.delta", "delta": "pienso"})()
        yield type(
            "Event",
            (),
            {"type": "response.output_text.delta", "delta": "documento"},
        )()
        yield FakeCompletedEvent()

    class FakeResponsesWithEvents:
        async def create(self, **kwargs):
            captured.update(kwargs)

            class Stream:
                def __aiter__(self):
                    return _fake_stream_events().__aiter__()

            return Stream()

    class PatchedOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.responses = FakeResponsesWithEvents()

    monkeypatch.setattr("openai.AsyncOpenAI", PatchedOpenAI)

    generation_config = GenerationConfig(
        openai_reasoning_effort="high",
        anthropic_thinking_budget_tokens=None,
    )
    result = await _generate_with_openai_responses_api(
        prompt="ping",
        model="gpt-5.4-mini",
        generation_config=generation_config,
    )

    assert result.generated_document == "documento"
    assert result.generation_reasoning == "pienso"
    assert result.token_usage is not None
    assert result.token_usage.thinking_tokens == 25
    assert captured["reasoning"] == {"effort": "high", "summary": "detailed"}
    assert "max_output_tokens" not in captured


@pytest.mark.asyncio
async def test_generate_with_anthropic_api_omits_top_p(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeOutputTokensDetails:
        thinking_tokens = 0

    class FakeUsage:
        input_tokens = 80
        output_tokens = 20
        output_tokens_details = FakeOutputTokensDetails()

    class FakeFinalMessage:
        usage = FakeUsage()
        content = []

    class FakeStream:
        def __init__(self) -> None:
            self.text_stream = self._iter()

        async def _iter(self):
            yield "hola"

        async def get_final_message(self):
            return FakeFinalMessage()

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

    generation_config = GenerationConfig(
        openai_reasoning_effort="none",
        anthropic_thinking_budget_tokens=None,
    )
    result = await _generate_with_anthropic_api(
        prompt="ping",
        model="claude-haiku-4-5-20251001",
        generation_config=generation_config,
    )

    assert result.generated_document == "hola"
    assert result.first_token_at is not None
    assert result.token_usage is not None
    assert result.token_usage.input_tokens == 80
    assert result.token_usage.output_tokens == 20
    assert result.token_usage.thinking_tokens == 0
    assert result.generation_reasoning is None
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == ANTHROPIC_EVAL_MAX_OUTPUT_TOKENS
    assert "top_p" not in captured
    assert "thinking" not in captured


@pytest.mark.asyncio
async def test_generate_with_anthropic_api_enables_thinking_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeOutputTokensDetails:
        thinking_tokens = 500

    class FakeUsage:
        input_tokens = 80
        output_tokens = 700
        output_tokens_details = FakeOutputTokensDetails()

    class FakeFinalMessage:
        usage = FakeUsage()
        content = [type("ThinkingBlock", (), {"thinking": "analizo el caso", "type": "thinking"})()]

    class FakeStream:
        @property
        def text_stream(self):
            return self._iter()

        async def _iter(self):
            if False:
                yield ""

        async def get_final_message(self):
            return FakeFinalMessage()

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
            self.messages = FakeMessages()

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeAnthropic)

    generation_config = GenerationConfig(
        openai_reasoning_effort="none",
        anthropic_thinking_budget_tokens=4096,
    )
    result = await _generate_with_anthropic_api(
        prompt="ping",
        model="claude-haiku-4-5-20251001",
        generation_config=generation_config,
    )

    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert captured["temperature"] == 1.0
    assert result.token_usage is not None
    assert result.token_usage.thinking_tokens == 500
    assert result.token_usage.output_tokens == 200
    assert result.generation_reasoning == "analizo el caso"


@pytest.mark.asyncio
async def test_judge_document_uses_high_reasoning_effort_for_gpt_5_4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evals.document_generation.run_eval import judge_document

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict[str, object] = {}
    parsed_result = JudgeResult(
        clinical_safety_score=5,
        faithfulness_score=5,
        template_adherence_score=5,
        uncertainty_handling_score=5,
        invented_info=[],
        missing_info=[],
        contradiction_info=[],
        dosing_error_info=[],
        verdict="pass",
        summary="ok",
    )

    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeChoice:
        def __init__(self, content: str) -> None:
            self.message = FakeMessage(content)

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self.choices = [FakeChoice(content)]

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse('{"summary":"ok"}')

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.chat = FakeChat()

    monkeypatch.setattr("openai.AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(
        "evals.document_generation.run_eval.render_judge_prompt",
        lambda *_args, **_kwargs: "judge prompt",
    )
    monkeypatch.setattr(
        "evals.document_generation.run_eval.parse_judge_response",
        lambda raw: parsed_result,
    )

    result, raw = await judge_document(
        case=EvalCase(
            id="case-1",
            template="## Demo",
            context="context",
            transcription="transcription",
        ),
        generated_document="generated",
        judge_provider="openai",
        judge_model="gpt-5.4",
        judge_prompt_version="clinical_document_judge_v002",
    )

    assert result == parsed_result
    assert raw == '{"summary":"ok"}'
    assert captured["model"] == "gpt-5.4"
    assert captured["reasoning_effort"] == "high"
    assert "temperature" not in captured
    assert captured["response_format"] == {"type": "json_object"}
