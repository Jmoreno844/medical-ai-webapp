from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


EVALS_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    template: str
    context: str
    transcription: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ModelSpec:
    alias: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class JudgeResult:
    overall_score: int
    clinical_safety_score: int
    faithfulness_score: int
    template_adherence_score: int
    uncertainty_handling_score: int
    missing_or_invented_info: list[str]
    verdict: str
    summary: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    time_to_first_token_ms: int
    time_after_first_token_ms: int
    total_generation_ms: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _load_case_template(item: dict[str, object]) -> str:
    template = str(item.get("template", "")).strip()
    template_file = str(item.get("template_file", "")).strip()
    if template and template_file:
        raise ValueError("case_cannot_define_template_and_template_file_together")
    if template:
        return template
    if template_file:
        path = EVALS_ROOT / template_file
        if not path.exists():
            raise FileNotFoundError(f"case_template_file_not_found: {template_file}")
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_cases(path: Path) -> list[EvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("cases_file_must_be_a_list")

    cases: list[EvalCase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"case_{index}_must_be_an_object")
        case_id = str(item.get("id", "")).strip()
        template = _load_case_template(item)
        context = str(item.get("context", "")).strip()
        transcription = str(item.get("transcription", "")).strip()
        notes = item.get("notes")
        if not case_id or not template or not context or not transcription:
            raise ValueError(f"case_{index}_is_missing_required_fields")
        cases.append(
            EvalCase(
                id=case_id,
                template=template,
                context=context,
                transcription=transcription,
                notes=str(notes).strip() if notes else None,
            )
        )
    return cases


def select_cases(
    cases: list[EvalCase],
    *,
    count: int | None = None,
    case_id: str | None = None,
) -> list[EvalCase]:
    selected = cases
    if case_id:
        normalized = case_id.strip()
        selected = [case for case in selected if case.id == normalized]
        if not selected:
            raise ValueError(f"case_id_not_found: {normalized}")
    if count is not None:
        if count <= 0:
            raise ValueError("count_must_be_positive")
        selected = selected[:count]
    return selected


def load_prompt_version(prompt_version: str) -> str:
    path = EVALS_ROOT / "prompts" / f"{prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt_version_not_found: {prompt_version}")
    return path.read_text(encoding="utf-8").strip()


def load_judge_prompt(judge_prompt_version: str) -> str:
    path = EVALS_ROOT / "judges" / f"{judge_prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"judge_prompt_version_not_found: {judge_prompt_version}"
        )
    return path.read_text(encoding="utf-8").strip()


def render_generation_prompt(prompt_template: str, case: EvalCase) -> str:
    return prompt_template.format(
        template=case.template,
        context=case.context,
        transcription=case.transcription,
    )


def render_judge_prompt(
    judge_template: str,
    *,
    case: EvalCase,
    generated_document: str,
) -> str:
    return judge_template.format(
        template=case.template,
        context=case.context,
        transcription=case.transcription,
        generated_document=generated_document,
    )


def parse_model_specs(raw: str) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    aliases_seen: set[str] = set()
    provider_map = {
        "gemini": "google_genai",
        "google": "google_genai",
        "google_genai": "google_genai",
        "anthropic": "anthropic_api",
        "claude": "anthropic_api",
        "anthropic_api": "anthropic_api",
        "anthropic_vertex": "anthropic_vertex",
    }
    for item in raw.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        alias, sep, model = normalized.partition(":")
        alias = alias.strip().lower()
        model = model.strip()
        if not sep or not alias or not model:
            raise ValueError(f"invalid_model_spec: {normalized}")
        provider = provider_map.get(alias)
        if provider is None:
            raise ValueError(f"unsupported_model_alias: {alias}")
        if alias in aliases_seen:
            raise ValueError(f"duplicate_model_alias: {alias}")
        aliases_seen.add(alias)
        specs.append(ModelSpec(alias=alias, provider=provider, model=model))
    if not specs:
        raise ValueError("at_least_one_model_is_required")
    return specs


def extract_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    text = text.strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue
    raise ValueError("judge_response_did_not_contain_valid_json_object")


def parse_judge_response(raw: str) -> JudgeResult:
    payload = extract_json_object(raw)
    required_ints = {
        "overall_score",
        "clinical_safety_score",
        "faithfulness_score",
        "template_adherence_score",
        "uncertainty_handling_score",
    }
    missing = required_ints.difference(payload)
    missing.update(
        {
            "missing_or_invented_info",
            "verdict",
            "summary",
        }.difference(payload)
    )
    if missing:
        joined = ", ".join(sorted(missing))
        raise ValueError(f"judge_response_missing_fields: {joined}")

    findings = payload["missing_or_invented_info"]
    if not isinstance(findings, list) or any(not isinstance(item, str) for item in findings):
        raise ValueError("judge_response_missing_or_invented_info_must_be_string_list")

    try:
        result = JudgeResult(
            overall_score=int(payload["overall_score"]),
            clinical_safety_score=int(payload["clinical_safety_score"]),
            faithfulness_score=int(payload["faithfulness_score"]),
            template_adherence_score=int(payload["template_adherence_score"]),
            uncertainty_handling_score=int(payload["uncertainty_handling_score"]),
            missing_or_invented_info=[item.strip() for item in findings if item.strip()],
            verdict=str(payload["verdict"]).strip(),
            summary=str(payload["summary"]).strip(),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("judge_response_contains_invalid_scalar_types") from exc

    if not result.verdict or not result.summary:
        raise ValueError("judge_response_verdict_and_summary_must_be_present")
    return result
