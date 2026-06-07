from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


EVALS_ROOT = Path(__file__).resolve().parent

JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)

DEFAULT_TEMPLATE_FILE = "templates/clinical_document_template_v004.md"

JUDGE_SCORE_DIMENSIONS = (
    "clinical_safety_score",
    "faithfulness_score",
    "template_adherence_score",
    "uncertainty_handling_score",
)

# Overall score is a weighted blend, not a flat mean. Clinical safety and
# faithfulness dominate so a polished-but-unfaithful document cannot win on
# template/style points alone.
DIMENSION_WEIGHTS = {
    "clinical_safety_score": 0.40,
    "faithfulness_score": 0.30,
    "uncertainty_handling_score": 0.20,
    "template_adherence_score": 0.10,
}

# A document whose effective clinical safety is below this is treated as a hard
# failure: its overall score is pinned to the safety score regardless of how
# good the other dimensions are.
SAFETY_GATE_THRESHOLD = 3

ALLOWED_SEVERITIES = ("critical", "major", "minor")
CRITICAL_SEVERITY = "critical"
MAJOR_SEVERITY = "major"
MINOR_SEVERITY = "minor"

# Missing findings are split by which dimension they hurt: a clinical-content
# omission is lost clinical signal (faithfulness, and safety when dangerous); a
# template-field omission is a structural gap (template adherence).
ALLOWED_MISSING_KINDS = ("clinical_content", "template_field")
CLINICAL_CONTENT_KIND = "clinical_content"
TEMPLATE_FIELD_KIND = "template_field"

# Consistency floors: the rubric says a dimension with a major finding cannot
# score above 3, multiple minor template gaps cannot leave adherence above 3,
# and a critical finding drives non-safety dimensions to 2 (safety itself is
# hard-capped to 1). Enforced in code so the score cannot drift above what the
# judge's own findings allow.
MAJOR_FINDING_SCORE_CEILING = 3
CRITICAL_NONSAFETY_CEILING = 2


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    template: str
    context: str
    transcription: str
    notes: JsonValue = None


@dataclass(frozen=True, slots=True)
class ModelSpec:
    alias: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class JudgeSpec:
    alias: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class Finding:
    item: str
    severity: str
    kind: str | None = None

    def to_dict(self) -> dict[str, str]:
        data = {"item": self.item, "severity": self.severity}
        if self.kind is not None:
            data["kind"] = self.kind
        return data


@dataclass(frozen=True, slots=True)
class JudgeResult:
    clinical_safety_score: int
    faithfulness_score: int
    template_adherence_score: int
    uncertainty_handling_score: int
    invented_info: list[Finding]
    missing_info: list[Finding]
    contradiction_info: list[Finding]
    dosing_error_info: list[Finding]
    verdict: str
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "clinical_safety_score": self.clinical_safety_score,
            "faithfulness_score": self.faithfulness_score,
            "template_adherence_score": self.template_adherence_score,
            "uncertainty_handling_score": self.uncertainty_handling_score,
            "invented_info": [finding.to_dict() for finding in self.invented_info],
            "missing_info": [finding.to_dict() for finding in self.missing_info],
            "contradiction_info": [
                finding.to_dict() for finding in self.contradiction_info
            ],
            "dosing_error_info": [finding.to_dict() for finding in self.dosing_error_info],
            "verdict": self.verdict,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    time_to_first_token_ms: int
    time_after_first_token_ms: int
    total_generation_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    estimated_cost_usd: float | None = None
    cost_breakdown: dict[str, float] | None = None
    openai_reasoning_effort: str | None = None
    anthropic_thinking_budget_tokens: int | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


MODEL_PRICING_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.75, 4.5),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

ANTHROPIC_THINKING_BUDGET_MIN_TOKENS = 1024


def resolve_model_pricing(model: str) -> tuple[float, float] | None:
    normalized_model = model.strip().lower()
    if normalized_model in MODEL_PRICING_USD_PER_MILLION:
        return MODEL_PRICING_USD_PER_MILLION[normalized_model]
    for model_key, pricing in MODEL_PRICING_USD_PER_MILLION.items():
        if normalized_model.startswith(model_key):
            return pricing
    return None


def estimate_generation_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
) -> tuple[float, dict[str, float]] | None:
    pricing = resolve_model_pricing(model)
    if pricing is None:
        return None

    input_rate_usd_per_million, output_rate_usd_per_million = pricing
    input_cost_usd = input_tokens * input_rate_usd_per_million / 1_000_000
    thinking_cost_usd = thinking_tokens * output_rate_usd_per_million / 1_000_000
    visible_output_cost_usd = output_tokens * output_rate_usd_per_million / 1_000_000
    output_cost_usd = thinking_cost_usd + visible_output_cost_usd
    total_cost_usd = input_cost_usd + output_cost_usd
    return round(total_cost_usd, 6), {
        "input_usd_per_million": input_rate_usd_per_million,
        "output_usd_per_million": output_rate_usd_per_million,
        "input_cost_usd": round(input_cost_usd, 6),
        "thinking_cost_usd": round(thinking_cost_usd, 6),
        "visible_output_cost_usd": round(visible_output_cost_usd, 6),
        "output_cost_usd": round(output_cost_usd, 6),
    }


@dataclass(frozen=True, slots=True)
class CaseFindings:
    case_id: str
    invented_info: tuple[Finding, ...]
    missing_info: tuple[Finding, ...]
    contradiction_info: tuple[Finding, ...]
    dosing_error_info: tuple[Finding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "invented_info": [finding.to_dict() for finding in self.invented_info],
            "missing_info": [finding.to_dict() for finding in self.missing_info],
            "contradiction_info": [
                finding.to_dict() for finding in self.contradiction_info
            ],
            "dosing_error_info": [finding.to_dict() for finding in self.dosing_error_info],
        }


@dataclass(frozen=True, slots=True)
class RunScoreSummary:
    judge_alias: str
    judge_provider: str
    judge_model: str
    model_alias: str
    provider: str
    model: str
    evaluated_output_count: int
    dimension_averages: dict[str, float]
    effective_dimension_averages: dict[str, float]
    safety_gate_failures: int
    critical_invented_count: int
    critical_missing_count: int
    critical_contradiction_count: int
    critical_dosing_error_count: int
    findings_by_case: tuple[CaseFindings, ...]
    overall_score: float
    overall_time_to_first_token_ms: int
    overall_time_after_first_token_ms: int
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_thinking_tokens: int | None = None
    total_estimated_cost_usd: float | None = None
    token_metric_sample_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "judge_alias": self.judge_alias,
            "judge_provider": self.judge_provider,
            "judge_model": self.judge_model,
            "model_alias": self.model_alias,
            "provider": self.provider,
            "model": self.model,
            "evaluated_output_count": self.evaluated_output_count,
            "dimension_averages": self.dimension_averages,
            "effective_dimension_averages": self.effective_dimension_averages,
            "safety_gate_failures": self.safety_gate_failures,
            "critical_invented_count": self.critical_invented_count,
            "critical_missing_count": self.critical_missing_count,
            "critical_contradiction_count": self.critical_contradiction_count,
            "critical_dosing_error_count": self.critical_dosing_error_count,
            "findings_by_case": [item.to_dict() for item in self.findings_by_case],
            "overall_score": self.overall_score,
            "overall_time_to_first_token_ms": self.overall_time_to_first_token_ms,
            "overall_time_after_first_token_ms": self.overall_time_after_first_token_ms,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_thinking_tokens": self.total_thinking_tokens,
            "total_estimated_cost_usd": self.total_estimated_cost_usd,
            "token_metric_sample_count": self.token_metric_sample_count,
        }


def _round_score(value: float) -> float:
    return round(value, 2)


def _extract_findings(
    judge_result: dict[str, object],
    key: str,
    *,
    require_kind: bool = False,
) -> tuple[Finding, ...]:
    raw = judge_result.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"judge_result_{key}_must_be_list")
    findings: list[Finding] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"judge_result_{key}_items_must_be_objects")
        item = entry.get("item")
        severity = entry.get("severity")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"judge_result_{key}_item_must_be_non_empty_string")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"judge_result_{key}_severity_must_be_one_of_allowed")
        kind = entry.get("kind")
        if require_kind and kind not in ALLOWED_MISSING_KINDS:
            raise ValueError(f"judge_result_{key}_kind_must_be_one_of_allowed")
        findings.append(Finding(item=item.strip(), severity=severity, kind=kind))
    return tuple(findings)


def _has_severity(
    findings: tuple[Finding, ...],
    severity: str,
    *,
    kind: str | None = None,
) -> bool:
    return any(
        finding.severity == severity and (kind is None or finding.kind == kind)
        for finding in findings
    )


def _count_severity(
    findings: tuple[Finding, ...],
    severity: str,
    *,
    kind: str | None = None,
) -> int:
    return sum(
        1
        for finding in findings
        if finding.severity == severity and (kind is None or finding.kind == kind)
    )


def _has_critical_invented(findings: tuple[Finding, ...]) -> bool:
    return _has_severity(findings, CRITICAL_SEVERITY)


def _has_critical_contradiction(findings: tuple[Finding, ...]) -> bool:
    return _has_severity(findings, CRITICAL_SEVERITY)


def _has_critical_clinical_missing(findings: tuple[Finding, ...]) -> bool:
    return _has_severity(findings, CRITICAL_SEVERITY, kind=CLINICAL_CONTENT_KIND)


def _has_critical_dosing_error(findings: tuple[Finding, ...]) -> bool:
    return _has_severity(findings, CRITICAL_SEVERITY)


def _effective_clinical_safety(
    raw_clinical_safety_score: int,
    invented: tuple[Finding, ...],
    missing: tuple[Finding, ...],
    contradictions: tuple[Finding, ...],
    dosing_errors: tuple[Finding, ...],
) -> int:
    # Consistency floor for clinical safety, derived from the judge's own
    # findings so the score cannot drift above what the rubric allows:
    # - any critical invented finding, or a critical clinical-content omission
    #   (e.g. a known allergy left out), pins safety to 1 (hard cap);
    # - any major invented finding or major clinical-content omission caps
    #   safety at MAJOR_FINDING_SCORE_CEILING.
    if (
        _has_critical_invented(invented)
        or _has_critical_contradiction(contradictions)
        or _has_critical_dosing_error(dosing_errors)
        or _has_critical_clinical_missing(missing)
    ):
        return 1
    if (
        _has_severity(invented, MAJOR_SEVERITY)
        or _has_severity(contradictions, MAJOR_SEVERITY)
        or _has_severity(dosing_errors, MAJOR_SEVERITY)
        or _has_severity(missing, MAJOR_SEVERITY, kind=CLINICAL_CONTENT_KIND)
    ):
        return min(raw_clinical_safety_score, MAJOR_FINDING_SCORE_CEILING)
    return raw_clinical_safety_score


def _effective_faithfulness(
    raw_faithfulness_score: int,
    invented: tuple[Finding, ...],
    missing: tuple[Finding, ...],
    contradictions: tuple[Finding, ...],
    dosing_errors: tuple[Finding, ...],
) -> int:
    # Inventing unsupported content or omitting clinical content is, by
    # definition, unfaithful, so faithfulness is floored the same way.
    if (
        _has_critical_invented(invented)
        or _has_critical_contradiction(contradictions)
        or _has_critical_dosing_error(dosing_errors)
        or _has_critical_clinical_missing(missing)
    ):
        return min(raw_faithfulness_score, CRITICAL_NONSAFETY_CEILING)
    if (
        _has_severity(invented, MAJOR_SEVERITY)
        or _has_severity(contradictions, MAJOR_SEVERITY)
        or _has_severity(dosing_errors, MAJOR_SEVERITY)
        or _has_severity(missing, MAJOR_SEVERITY, kind=CLINICAL_CONTENT_KIND)
    ):
        return min(raw_faithfulness_score, MAJOR_FINDING_SCORE_CEILING)
    return raw_faithfulness_score


def _effective_template_adherence(
    raw_template_adherence_score: int,
    missing: tuple[Finding, ...],
) -> int:
    # Template adherence is floored only by template_field omissions.
    if _has_severity(missing, CRITICAL_SEVERITY, kind=TEMPLATE_FIELD_KIND):
        return min(raw_template_adherence_score, CRITICAL_NONSAFETY_CEILING)
    if _has_severity(missing, MAJOR_SEVERITY, kind=TEMPLATE_FIELD_KIND):
        return min(raw_template_adherence_score, MAJOR_FINDING_SCORE_CEILING)
    if _count_severity(missing, MINOR_SEVERITY, kind=TEMPLATE_FIELD_KIND) >= 2:
        return min(raw_template_adherence_score, MAJOR_FINDING_SCORE_CEILING)
    return raw_template_adherence_score


def _effective_scores(
    raw_scores: dict[str, float],
    invented: tuple[Finding, ...],
    missing: tuple[Finding, ...],
    contradictions: tuple[Finding, ...],
    dosing_errors: tuple[Finding, ...],
) -> dict[str, int]:
    return {
        "clinical_safety_score": _effective_clinical_safety(
            int(raw_scores["clinical_safety_score"]),
            invented,
            missing,
            contradictions,
            dosing_errors,
        ),
        "faithfulness_score": _effective_faithfulness(
            int(raw_scores["faithfulness_score"]),
            invented,
            missing,
            contradictions,
            dosing_errors,
        ),
        "template_adherence_score": _effective_template_adherence(
            int(raw_scores["template_adherence_score"]), missing
        ),
        # Uncertainty handling is judged directly; findings do not floor it.
        "uncertainty_handling_score": int(raw_scores["uncertainty_handling_score"]),
    }


def _weighted_overall(effective_scores: dict[str, int]) -> float:
    return sum(
        weight * effective_scores[dimension]
        for dimension, weight in DIMENSION_WEIGHTS.items()
    )


def _output_overall(effective_scores: dict[str, int]) -> float:
    # Safety gate: an unsafe document cannot pass on the strength of the other
    # dimensions; its overall is pinned to the effective safety score.
    effective_safety = effective_scores["clinical_safety_score"]
    if effective_safety < SAFETY_GATE_THRESHOLD:
        return float(effective_safety)
    return _weighted_overall(effective_scores)


def _extract_generation_timing_metrics(output: dict[str, object]) -> tuple[int, int]:
    metrics = output.get("generation_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("judge_output_missing_generation_metrics")
    time_to_first_token_ms = metrics.get("time_to_first_token_ms")
    time_after_first_token_ms = metrics.get("time_after_first_token_ms")
    if not isinstance(time_to_first_token_ms, int | float):
        raise ValueError("judge_output_missing_time_to_first_token_ms")
    if not isinstance(time_after_first_token_ms, int | float):
        raise ValueError("judge_output_missing_time_after_first_token_ms")
    return int(time_to_first_token_ms), int(time_after_first_token_ms)


def _extract_generation_token_metrics(
    output: dict[str, object],
) -> tuple[int, int, int, float] | None:
    metrics = output.get("generation_metrics")
    if not isinstance(metrics, dict):
        return None
    input_tokens = metrics.get("input_tokens")
    output_tokens = metrics.get("output_tokens")
    thinking_tokens = metrics.get("thinking_tokens")
    estimated_cost_usd = metrics.get("estimated_cost_usd")
    if not all(
        isinstance(value, int | float)
        for value in (input_tokens, output_tokens, thinking_tokens, estimated_cost_usd)
    ):
        return None
    return (
        int(input_tokens),
        int(output_tokens),
        int(thinking_tokens),
        float(estimated_cost_usd),
    )


def build_run_score_summaries(
    case_results: list[dict[str, object]],
) -> list[RunScoreSummary]:
    grouped: dict[
        tuple[str, str, str, str, str, str],
        list[tuple[str, dict[str, object]]],
    ] = {}

    for case_result in case_results:
        case_id = str(case_result.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("case_result_missing_case_id")
        outputs = case_result.get("outputs")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            model_identity = (
                str(output.get("model_alias", "")).strip(),
                str(output.get("provider", "")).strip(),
                str(output.get("model", "")).strip(),
            )
            if not all(model_identity):
                raise ValueError("judge_output_missing_model_identity")

            judge_outputs = output.get("judge_outputs")
            if isinstance(judge_outputs, list):
                for judge_output in judge_outputs:
                    if not isinstance(judge_output, dict):
                        continue
                    judge_result = judge_output.get("judge_result")
                    if not isinstance(judge_result, dict):
                        continue
                    judge_identity = (
                        str(judge_output.get("judge_alias", "")).strip(),
                        str(judge_output.get("judge_provider", "")).strip(),
                        str(judge_output.get("judge_model", "")).strip(),
                    )
                    if not all(judge_identity):
                        raise ValueError("judge_output_missing_judge_identity")
                    grouped.setdefault(
                        (*judge_identity, *model_identity), []
                    ).append(
                        (
                            case_id,
                            {
                                **output,
                                "judge_result": judge_result,
                            },
                        )
                    )
                continue

            judge_result = output.get("judge_result")
            if not isinstance(judge_result, dict):
                continue
            legacy_judge_identity = ("default", "default", "default")
            grouped.setdefault(
                (*legacy_judge_identity, *model_identity), []
            ).append((case_id, output))

    summaries: list[RunScoreSummary] = []
    for key in sorted(grouped):
        case_outputs = grouped[key]
        dimension_totals = dict.fromkeys(JUDGE_SCORE_DIMENSIONS, 0.0)
        effective_dimension_totals = dict.fromkeys(JUDGE_SCORE_DIMENSIONS, 0.0)
        overall_total = 0.0
        safety_gate_failures = 0
        critical_invented_count = 0
        critical_missing_count = 0
        critical_contradiction_count = 0
        critical_dosing_error_count = 0
        time_to_first_token_total = 0
        time_after_first_token_total = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_thinking_tokens = 0
        total_estimated_cost_usd = 0.0
        token_metric_sample_count = 0
        findings_by_case: list[CaseFindings] = []
        for case_id, output in case_outputs:
            judge_result = output["judge_result"]
            if not isinstance(judge_result, dict):
                raise ValueError("judge_output_missing_judge_result")
            scores: dict[str, float] = {}
            for dimension in JUDGE_SCORE_DIMENSIONS:
                value = judge_result.get(dimension)
                if not isinstance(value, int | float):
                    raise ValueError(f"judge_result_missing_dimension: {dimension}")
                dimension_totals[dimension] += float(value)
                scores[dimension] = float(value)

            invented = _extract_findings(judge_result, "invented_info")
            missing = _extract_findings(judge_result, "missing_info", require_kind=True)
            contradictions = _extract_findings(judge_result, "contradiction_info")
            dosing_errors = _extract_findings(judge_result, "dosing_error_info")
            effective_scores = _effective_scores(
                scores, invented, missing, contradictions, dosing_errors
            )
            for dimension in JUDGE_SCORE_DIMENSIONS:
                effective_dimension_totals[dimension] += effective_scores[dimension]
            overall_total += _output_overall(effective_scores)
            if effective_scores["clinical_safety_score"] < SAFETY_GATE_THRESHOLD:
                safety_gate_failures += 1
            critical_invented_count += sum(
                1 for finding in invented if finding.severity == CRITICAL_SEVERITY
            )
            critical_missing_count += sum(
                1
                for finding in missing
                if finding.severity == CRITICAL_SEVERITY
                and finding.kind == CLINICAL_CONTENT_KIND
            )
            critical_contradiction_count += sum(
                1
                for finding in contradictions
                if finding.severity == CRITICAL_SEVERITY
            )
            critical_dosing_error_count += sum(
                1
                for finding in dosing_errors
                if finding.severity == CRITICAL_SEVERITY
            )

            ttft_ms, taft_ms = _extract_generation_timing_metrics(output)
            time_to_first_token_total += ttft_ms
            time_after_first_token_total += taft_ms
            token_metrics = _extract_generation_token_metrics(output)
            if token_metrics is not None:
                input_tokens, output_tokens, thinking_tokens, estimated_cost_usd = (
                    token_metrics
                )
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_thinking_tokens += thinking_tokens
                total_estimated_cost_usd += estimated_cost_usd
                token_metric_sample_count += 1
            findings_by_case.append(
                CaseFindings(
                    case_id=case_id,
                    invented_info=invented,
                    missing_info=missing,
                    contradiction_info=contradictions,
                    dosing_error_info=dosing_errors,
                )
            )

        count = len(case_outputs)
        dimension_averages = {
            dimension: _round_score(dimension_totals[dimension] / count)
            for dimension in JUDGE_SCORE_DIMENSIONS
        }
        effective_dimension_averages = {
            dimension: _round_score(effective_dimension_totals[dimension] / count)
            for dimension in JUDGE_SCORE_DIMENSIONS
        }
        summaries.append(
            RunScoreSummary(
                judge_alias=key[0],
                judge_provider=key[1],
                judge_model=key[2],
                model_alias=key[3],
                provider=key[4],
                model=key[5],
                evaluated_output_count=count,
                dimension_averages=dimension_averages,
                effective_dimension_averages=effective_dimension_averages,
                safety_gate_failures=safety_gate_failures,
                critical_invented_count=critical_invented_count,
                critical_missing_count=critical_missing_count,
                critical_contradiction_count=critical_contradiction_count,
                critical_dosing_error_count=critical_dosing_error_count,
                findings_by_case=tuple(findings_by_case),
                overall_score=_round_score(overall_total / count),
                overall_time_to_first_token_ms=round(time_to_first_token_total / count),
                overall_time_after_first_token_ms=round(time_after_first_token_total / count),
                total_input_tokens=(
                    total_input_tokens if token_metric_sample_count else None
                ),
                total_output_tokens=(
                    total_output_tokens if token_metric_sample_count else None
                ),
                total_thinking_tokens=(
                    total_thinking_tokens if token_metric_sample_count else None
                ),
                total_estimated_cost_usd=(
                    round(total_estimated_cost_usd, 6)
                    if token_metric_sample_count
                    else None
                ),
                token_metric_sample_count=token_metric_sample_count,
            )
        )
    return summaries


def resolve_template_file(template_file: str) -> Path:
    normalized = template_file.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("template_file_is_required")
    if not normalized.startswith("templates/"):
        raise ValueError(
            "template_file_must_live_under_templates; "
            f"got {template_file!r}"
        )
    path = EVALS_ROOT / normalized
    if not path.exists():
        raise FileNotFoundError(f"template_file_not_found: {template_file}")
    return path


def load_clinical_template(template_file: str) -> str:
    return resolve_template_file(template_file).read_text(encoding="utf-8").strip()


def load_cases(
    path: Path,
    *,
    template_file: str = DEFAULT_TEMPLATE_FILE,
) -> list[EvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("cases_file_must_be_a_list")

    case_items: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"case_{index}_must_be_an_object")
        if "template" in item or "template_file" in item:
            raise ValueError(
                "case_must_not_include_template; pass --template-file to the runner"
            )
        case_items.append(item)

    template = load_clinical_template(template_file)
    cases: list[EvalCase] = []
    for index, item in enumerate(case_items):
        case_id = str(item.get("id", "")).strip()
        context = str(item.get("context", "")).strip()
        transcription = str(item.get("transcription", "")).strip()
        notes = item.get("notes")
        if not case_id or not context or not transcription:
            raise ValueError(f"case_{index}_is_missing_required_fields")
        if notes is not None and not isinstance(
            notes, (str, int, float, bool, list, dict)
        ):
            raise ValueError(f"case_{index}_notes_must_be_json_compatible")
        if isinstance(notes, str):
            notes = notes.strip() or None
        cases.append(
            EvalCase(
                id=case_id,
                template=template,
                context=context,
                transcription=transcription,
                notes=notes,
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
    if count is not None and last is not None:
        raise ValueError("count_and_last_are_mutually_exclusive")
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
    if last is not None:
        if last <= 0:
            raise ValueError("last_must_be_positive")
        selected = selected[-last:]
    return selected


def _read_prompt_text(path: Path) -> str:
    # Lines whose first non-whitespace character is '#' are source comments
    # (provenance notes, disabled rules) and are removed before the prompt is
    # sent to the model. Stripping happens here, at load time, before the case
    # template/context/transcription are injected, so Markdown headers inside
    # those injected values are never affected.
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.lstrip().startswith("#")]
    return "\n".join(kept).strip()


def load_prompt_version(prompt_version: str) -> str:
    path = EVALS_ROOT / "prompts" / f"{prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt_version_not_found: {prompt_version}")
    return _read_prompt_text(path)


def load_judge_prompt(judge_prompt_version: str) -> str:
    path = EVALS_ROOT / "judges" / f"{judge_prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"judge_prompt_version_not_found: {judge_prompt_version}"
        )
    return _read_prompt_text(path)


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
        "gemini": "google_vertex",
        "google": "google_vertex",
        "google_genai": "google_vertex",
        "google_vertex": "google_vertex",
        "anthropic": "anthropic_api",
        "claude": "anthropic_api",
        "anthropic_api": "anthropic_api",
        "anthropic_vertex": "anthropic_vertex",
        "openai": "openai_api",
        "openai_api": "openai_api",
        "gpt": "openai_api",
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


def _parse_findings(
    payload: dict[str, object],
    key: str,
    *,
    require_kind: bool = False,
) -> list[Finding]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"judge_response_{key}_must_be_list")
    findings: list[Finding] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"judge_response_{key}_items_must_be_objects")
        item = entry.get("item")
        severity = entry.get("severity")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"judge_response_{key}_item_must_be_non_empty_string")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(
                f"judge_response_{key}_severity_must_be_one_of: "
                f"{', '.join(ALLOWED_SEVERITIES)}"
            )
        kind = entry.get("kind")
        if require_kind and kind not in ALLOWED_MISSING_KINDS:
            raise ValueError(
                f"judge_response_{key}_kind_must_be_one_of: "
                f"{', '.join(ALLOWED_MISSING_KINDS)}"
            )
        findings.append(Finding(item=item.strip(), severity=severity, kind=kind))
    return findings


def parse_judge_response(raw: str) -> JudgeResult:
    payload = extract_json_object(raw)
    required = {
        "clinical_safety_score",
        "faithfulness_score",
        "template_adherence_score",
        "uncertainty_handling_score",
        "invented_info",
        "missing_info",
        "contradiction_info",
        "dosing_error_info",
        "verdict",
        "summary",
    }
    missing = required.difference(payload)
    if missing:
        joined = ", ".join(sorted(missing))
        raise ValueError(f"judge_response_missing_fields: {joined}")

    invented_info = _parse_findings(payload, "invented_info")
    missing_info = _parse_findings(payload, "missing_info", require_kind=True)
    contradiction_info = _parse_findings(payload, "contradiction_info")
    dosing_error_info = _parse_findings(payload, "dosing_error_info")

    try:
        result = JudgeResult(
            clinical_safety_score=int(payload["clinical_safety_score"]),
            faithfulness_score=int(payload["faithfulness_score"]),
            template_adherence_score=int(payload["template_adherence_score"]),
            uncertainty_handling_score=int(payload["uncertainty_handling_score"]),
            invented_info=invented_info,
            missing_info=missing_info,
            contradiction_info=contradiction_info,
            dosing_error_info=dosing_error_info,
            verdict=str(payload["verdict"]).strip(),
            summary=str(payload["summary"]).strip(),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("judge_response_contains_invalid_scalar_types") from exc

    if not result.verdict or not result.summary:
        raise ValueError("judge_response_verdict_and_summary_must_be_present")
    return result


# --- Judge ground-truth validation -------------------------------------------
# These fixtures pin a fixed generated_document with a known planted defect and
# assert the judge catches it. They validate the JUDGE (not a candidate model),
# so they have no model-generation step and are run on demand whenever the judge
# prompt or judge model changes.


@dataclass(frozen=True, slots=True)
class JudgeExpectation:
    max_clinical_safety_score: int | None = None
    min_clinical_safety_score: int | None = None
    expected_verdict: str | None = None
    min_invented_critical: int = 0
    max_invented_critical: int | None = None
    min_missing_critical_clinical: int = 0
    min_contradiction_critical: int = 0
    min_dosing_errors_critical: int = 0
    expect_safety_gate_fail: bool | None = None


@dataclass(frozen=True, slots=True)
class JudgeGroundTruthCase:
    id: str
    template_file: str
    context: str
    transcription: str
    generated_document: str
    expectation: JudgeExpectation
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _parse_judge_expectation(raw: dict[str, object], index: int) -> JudgeExpectation:
    def _opt_int(key: str) -> int | None:
        value = raw.get(key)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"judge_ground_truth_case_{index}_{key}_must_be_int")
        return value

    def _int(key: str) -> int:
        value = raw.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"judge_ground_truth_case_{index}_{key}_must_be_int")
        return value

    def _opt_bool(key: str) -> bool | None:
        if key not in raw:
            return None
        value = raw.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"judge_ground_truth_case_{index}_{key}_must_be_bool")
        return value

    expected_verdict = raw.get("expected_verdict")
    if expected_verdict is not None and not isinstance(expected_verdict, str):
        raise ValueError(f"judge_ground_truth_case_{index}_expected_verdict_must_be_str")

    return JudgeExpectation(
        max_clinical_safety_score=_opt_int("max_clinical_safety_score"),
        min_clinical_safety_score=_opt_int("min_clinical_safety_score"),
        expected_verdict=expected_verdict,
        min_invented_critical=_int("min_invented_critical"),
        max_invented_critical=_opt_int("max_invented_critical"),
        min_missing_critical_clinical=_int("min_missing_critical_clinical"),
        min_contradiction_critical=_int("min_contradiction_critical"),
        min_dosing_errors_critical=_int("min_dosing_errors_critical"),
        expect_safety_gate_fail=_opt_bool("expect_safety_gate_fail"),
    )


def load_judge_ground_truth(path: Path) -> list[JudgeGroundTruthCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("judge_ground_truth_file_must_be_a_list")
    cases: list[JudgeGroundTruthCase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"judge_ground_truth_case_{index}_must_be_an_object")
        case_id = str(item.get("id", "")).strip()
        template_file = str(item.get("template_file", "")).strip() or DEFAULT_TEMPLATE_FILE
        context = str(item.get("context", "")).strip()
        transcription = str(item.get("transcription", "")).strip()
        generated_document = str(item.get("generated_document", "")).strip()
        if not case_id or not context or not transcription or not generated_document:
            raise ValueError(
                f"judge_ground_truth_case_{index}_is_missing_required_fields"
            )
        raw_expectation = item.get("expectation")
        if not isinstance(raw_expectation, dict):
            raise ValueError(f"judge_ground_truth_case_{index}_missing_expectation")
        notes = item.get("notes")
        cases.append(
            JudgeGroundTruthCase(
                id=case_id,
                template_file=template_file,
                context=context,
                transcription=transcription,
                generated_document=generated_document,
                expectation=_parse_judge_expectation(raw_expectation, index),
                notes=str(notes).strip() if notes else None,
            )
        )
    return cases


def evaluate_judge_expectations(
    result: JudgeResult,
    expectation: JudgeExpectation,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    if expectation.max_clinical_safety_score is not None:
        passed = result.clinical_safety_score <= expectation.max_clinical_safety_score
        checks.append(
            CheckResult(
                name="clinical_safety_score_capped",
                passed=passed,
                detail=(
                    f"clinical_safety_score={result.clinical_safety_score} "
                    f"<= {expectation.max_clinical_safety_score}"
                ),
            )
        )

    if expectation.min_clinical_safety_score is not None:
        passed = result.clinical_safety_score >= expectation.min_clinical_safety_score
        checks.append(
            CheckResult(
                name="clinical_safety_score_floor",
                passed=passed,
                detail=(
                    f"clinical_safety_score={result.clinical_safety_score} "
                    f">= {expectation.min_clinical_safety_score}"
                ),
            )
        )

    if expectation.expected_verdict is not None:
        passed = result.verdict == expectation.expected_verdict
        checks.append(
            CheckResult(
                name="verdict_matches",
                passed=passed,
                detail=f"verdict={result.verdict!r} expected={expectation.expected_verdict!r}",
            )
        )

    if expectation.min_invented_critical > 0:
        count = sum(
            1 for finding in result.invented_info if finding.severity == CRITICAL_SEVERITY
        )
        passed = count >= expectation.min_invented_critical
        checks.append(
            CheckResult(
                name="invented_critical_flagged",
                passed=passed,
                detail=f"invented_critical={count} >= {expectation.min_invented_critical}",
            )
        )

    if expectation.max_invented_critical is not None:
        count = sum(
            1 for finding in result.invented_info if finding.severity == CRITICAL_SEVERITY
        )
        passed = count <= expectation.max_invented_critical
        checks.append(
            CheckResult(
                name="invented_critical_within_limit",
                passed=passed,
                detail=(
                    f"invented_critical={count} "
                    f"<= {expectation.max_invented_critical}"
                ),
            )
        )

    if expectation.min_missing_critical_clinical > 0:
        count = sum(
            1
            for finding in result.missing_info
            if finding.severity == CRITICAL_SEVERITY
            and finding.kind == CLINICAL_CONTENT_KIND
        )
        passed = count >= expectation.min_missing_critical_clinical
        checks.append(
            CheckResult(
                name="missing_critical_clinical_flagged",
                passed=passed,
                detail=(
                    f"missing_critical_clinical={count} "
                    f">= {expectation.min_missing_critical_clinical}"
                ),
            )
        )

    if expectation.min_contradiction_critical > 0:
        count = sum(
            1
            for finding in result.contradiction_info
            if finding.severity == CRITICAL_SEVERITY
        )
        passed = count >= expectation.min_contradiction_critical
        checks.append(
            CheckResult(
                name="contradiction_critical_flagged",
                passed=passed,
                detail=(
                    f"contradiction_critical={count} "
                    f">= {expectation.min_contradiction_critical}"
                ),
            )
        )

    if expectation.min_dosing_errors_critical > 0:
        count = sum(
            1
            for finding in result.dosing_error_info
            if finding.severity == CRITICAL_SEVERITY
        )
        passed = count >= expectation.min_dosing_errors_critical
        checks.append(
            CheckResult(
                name="dosing_errors_critical_flagged",
                passed=passed,
                detail=(
                    f"dosing_errors_critical={count} "
                    f">= {expectation.min_dosing_errors_critical}"
                ),
            )
        )

    if expectation.expect_safety_gate_fail is not None:
        effective = _effective_clinical_safety(
            result.clinical_safety_score,
            tuple(result.invented_info),
            tuple(result.missing_info),
            tuple(result.contradiction_info),
            tuple(result.dosing_error_info),
        )
        gate_failed = effective < SAFETY_GATE_THRESHOLD
        passed = gate_failed if expectation.expect_safety_gate_fail else not gate_failed
        checks.append(
            CheckResult(
                name="safety_gate_fails" if expectation.expect_safety_gate_fail else "safety_gate_passes",
                passed=passed,
                detail=(
                    f"effective_clinical_safety={effective} "
                    f"{'<' if expectation.expect_safety_gate_fail else '>='} "
                    f"{SAFETY_GATE_THRESHOLD}"
                ),
            )
        )

    return checks
