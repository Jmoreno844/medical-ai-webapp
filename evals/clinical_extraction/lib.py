from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


EVALS_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = EVALS_ROOT / "prompts"
DEFAULT_EXTRACTION_PROMPT_VERSION = "v1"
ALLOWED_EXTRACTION_PROMPT_VERSIONS = ("v0", "v1")
EXTRACTION_PROMPT_RUNTIME_SOURCE = "clinical_extraction_worker/app/prompts.py"

JUDGE_SCORE_DIMENSIONS = (
    "faithfulness_score",
    "atomicity_score",
    "coding_score",
    "grounding_score",
)

ALLOWED_SEVERITIES = ("critical", "major", "minor")


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    transcript_json: dict[str, object]
    reference_mentions: dict[str, object]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ModelSpec:
    alias: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class Finding:
    item: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {"item": self.item, "severity": self.severity}


@dataclass(frozen=True, slots=True)
class JudgeResult:
    faithfulness_score: int
    atomicity_score: int
    coding_score: int
    grounding_score: int
    invented_mentions: list[Finding]
    missing_mentions: list[Finding]
    atomicity_issues: list[Finding]
    coding_issues: list[Finding]
    verdict: str
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "faithfulness_score": self.faithfulness_score,
            "atomicity_score": self.atomicity_score,
            "coding_score": self.coding_score,
            "grounding_score": self.grounding_score,
            "invented_mentions": [item.to_dict() for item in self.invented_mentions],
            "missing_mentions": [item.to_dict() for item in self.missing_mentions],
            "atomicity_issues": [item.to_dict() for item in self.atomicity_issues],
            "coding_issues": [item.to_dict() for item in self.coding_issues],
            "verdict": self.verdict,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class RunScoreSummary:
    model_alias: str
    provider: str
    model: str
    evaluated_output_count: int
    dimension_averages: dict[str, float]
    critical_invented_count: int
    critical_missing_count: int
    critical_atomicity_issue_count: int
    critical_coding_issue_count: int
    overall_score: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("clinical_extraction_cases_file_must_be_a_list")

    cases: list[EvalCase] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"clinical_extraction_case_{index}_must_be_an_object")
        case_id = item.get("id")
        transcript_json = item.get("transcript_json")
        reference_mentions = item.get("reference_mentions")
        notes = item.get("notes")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"clinical_extraction_case_{index}_id_must_be_non_empty")
        if not isinstance(transcript_json, dict):
            raise ValueError(
                f"clinical_extraction_case_{index}_transcript_json_must_be_object"
            )
        if not isinstance(reference_mentions, dict):
            raise ValueError(
                f"clinical_extraction_case_{index}_reference_mentions_must_be_object"
            )
        if notes is not None and not isinstance(notes, str):
            raise ValueError(f"clinical_extraction_case_{index}_notes_must_be_str")
        cases.append(
            EvalCase(
                id=case_id.strip(),
                transcript_json=transcript_json,
                reference_mentions=reference_mentions,
                notes=notes.strip() if isinstance(notes, str) else None,
            )
        )
    return cases


def select_cases(
    cases: list[EvalCase],
    *,
    count: int | None = None,
    last: int | None = None,
    case_id: str | None = None,
) -> list[EvalCase]:
    selected = cases
    if case_id:
        selected = [case for case in selected if case.id == case_id]
    if count is not None:
        selected = selected[:count]
    if last is not None:
        selected = selected[-last:]
    if case_id and not selected:
        raise ValueError(f"clinical_extraction_case_not_found: {case_id}")
    return selected


def parse_model_specs(raw: str) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    for item in raw.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        provider, sep, model = normalized.partition(":")
        if not sep or not provider.strip() or not model.strip():
            raise ValueError(
                "Invalid model spec. Expected provider:model, for example "
                "gemini:gemini-2.5-flash"
            )
        specs.append(
            ModelSpec(
                alias=provider.strip().lower(),
                provider=provider.strip().lower(),
                model=model.strip(),
            )
        )
    if not specs:
        raise ValueError("At least one model spec is required")
    return specs


def normalize_extraction_prompt_version(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in ALLOWED_EXTRACTION_PROMPT_VERSIONS:
        return normalized
    raise ValueError(
        "clinical_extraction_prompt_version_invalid: "
        f"{raw!r} (expected one of {', '.join(ALLOWED_EXTRACTION_PROMPT_VERSIONS)})"
    )


def extraction_prompt_log_path(version: str) -> Path:
    normalized = normalize_extraction_prompt_version(version)
    return PROMPTS_DIR / f"clinical_extraction_{normalized}.txt"


def load_extraction_prompt_log(version: str) -> str:
    path = extraction_prompt_log_path(version)
    if not path.exists():
        raise ValueError(f"clinical_extraction_prompt_log_not_found: {path.name}")
    return path.read_text(encoding="utf-8")


def load_judge_prompt(version: str) -> str:
    path = EVALS_ROOT / "judges" / f"{version}.txt"
    if not path.exists():
        raise ValueError(f"clinical_extraction_judge_prompt_not_found: {version}")
    return path.read_text(encoding="utf-8")


def render_judge_prompt(
    template: str,
    *,
    case: EvalCase,
    processed_mentions: dict[str, object],
    grounding_stats: dict[str, object],
) -> str:
    return template.format(
        case_id=case.id,
        transcript_json=json.dumps(case.transcript_json, ensure_ascii=False, indent=2),
        reference_mentions=json.dumps(
            case.reference_mentions, ensure_ascii=False, indent=2
        ),
        processed_mentions=json.dumps(
            processed_mentions, ensure_ascii=False, indent=2
        ),
        grounding_stats=json.dumps(grounding_stats, ensure_ascii=False, indent=2),
    )


def extract_json_object(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("judge_response_did_not_contain_valid_json_object") from exc
    if not isinstance(payload, dict):
        raise ValueError("judge_response_did_not_contain_valid_json_object")
    return payload


def _parse_findings(payload: dict[str, object], key: str) -> list[Finding]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"judge_response_{key}_must_be_list")
    findings: list[Finding] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"judge_response_{key}_items_must_be_objects")
        text = item.get("item")
        severity = item.get("severity")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"judge_response_{key}_item_must_be_non_empty_string")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(
                f"judge_response_{key}_severity_must_be_one_of: "
                f"{', '.join(ALLOWED_SEVERITIES)}"
            )
        findings.append(Finding(item=text.strip(), severity=severity))
    return findings


def parse_judge_response(raw: str) -> JudgeResult:
    payload = extract_json_object(raw)
    required = {
        "faithfulness_score",
        "atomicity_score",
        "coding_score",
        "grounding_score",
        "invented_mentions",
        "missing_mentions",
        "atomicity_issues",
        "coding_issues",
        "verdict",
        "summary",
    }
    missing = required.difference(payload)
    if missing:
        raise ValueError(
            "judge_response_missing_fields: " + ", ".join(sorted(missing))
        )

    try:
        result = JudgeResult(
            faithfulness_score=int(payload["faithfulness_score"]),
            atomicity_score=int(payload["atomicity_score"]),
            coding_score=int(payload["coding_score"]),
            grounding_score=int(payload["grounding_score"]),
            invented_mentions=_parse_findings(payload, "invented_mentions"),
            missing_mentions=_parse_findings(payload, "missing_mentions"),
            atomicity_issues=_parse_findings(payload, "atomicity_issues"),
            coding_issues=_parse_findings(payload, "coding_issues"),
            verdict=str(payload["verdict"]).strip(),
            summary=str(payload["summary"]).strip(),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("judge_response_contains_invalid_scalar_types") from exc

    if not result.verdict or not result.summary:
        raise ValueError("judge_response_verdict_and_summary_must_be_present")
    return result


def build_run_score_summaries(case_results: list[dict[str, object]]) -> list[RunScoreSummary]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for case_result in case_results:
        outputs = case_result.get("outputs")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            key = (
                str(output.get("model_alias") or ""),
                str(output.get("provider") or ""),
                str(output.get("model") or ""),
            )
            grouped.setdefault(key, []).append(output)

    summaries: list[RunScoreSummary] = []
    for key in sorted(grouped):
        outputs = grouped[key]
        dimension_totals = {dimension: 0.0 for dimension in JUDGE_SCORE_DIMENSIONS}
        critical_invented = 0
        critical_missing = 0
        critical_atomicity = 0
        critical_coding = 0

        judged_outputs = [
            output
            for output in outputs
            if isinstance(output.get("judge_result"), dict)
        ]
        for output in judged_outputs:
            judge_result = output["judge_result"]
            for dimension in JUDGE_SCORE_DIMENSIONS:
                dimension_totals[dimension] += float(judge_result.get(dimension, 0))
            critical_invented += _count_critical(judge_result.get("invented_mentions"))
            critical_missing += _count_critical(judge_result.get("missing_mentions"))
            critical_atomicity += _count_critical(judge_result.get("atomicity_issues"))
            critical_coding += _count_critical(judge_result.get("coding_issues"))

        count = len(judged_outputs) or 1
        averages = {
            dimension: round(total / count, 2)
            for dimension, total in dimension_totals.items()
        }
        overall = round(sum(averages.values()) / len(JUDGE_SCORE_DIMENSIONS), 2)
        summaries.append(
            RunScoreSummary(
                model_alias=key[0],
                provider=key[1],
                model=key[2],
                evaluated_output_count=len(judged_outputs),
                dimension_averages=averages,
                critical_invented_count=critical_invented,
                critical_missing_count=critical_missing,
                critical_atomicity_issue_count=critical_atomicity,
                critical_coding_issue_count=critical_coding,
                overall_score=overall,
            )
        )
    return summaries


def _count_critical(raw_findings: object) -> int:
    if not isinstance(raw_findings, list):
        return 0
    count = 0
    for item in raw_findings:
        if isinstance(item, dict) and item.get("severity") == "critical":
            count += 1
    return count
