from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from classification.lib import ClusterCase, build_cluster_turns, cluster_to_payload_item
from common.case_paths import CLUSTER_CASES_INDEX
from common.context_spans import (
    Directive,
    SectionContext,
    SectionEvidence,
    transcript_directives,
    transcript_directives_for_section,
)
from common.json_utils import extract_json_object
from common.output_detail import DEFAULT_OUTPUT_DETAIL
from common.prompt_registry import (
    is_py_prompt_version,
    load_py_prompt_module,
    py_system_prompt,
)
from common.prompts import (
    DEFAULT_PROMPT_VERSION,
)
from common.prompts import (
    load_prompt as load_prompt_from_file,
)
from common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)
from common.templates import (
    ClinicalTemplate,
    TemplateSection,
    compose_section_guidelines,
    resolve_generation_mode,
)
from generation.evidence_markers import (
    CONTEXT_BRIEF_EVIDENCE_ID,
    parse_linked_plaintext,
)

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "generation"
PY_GENERATION_DIRECT_STEP = "generation_direct"
PY_GENERATION_PLANNER_STEP = "generation_planner"
PY_GENERATION_RENDERER_STEP = "generation_renderer"
PY_GENERATION_PROMPT_VERSIONS = frozenset({"v001"})
DEFAULT_CLASSIFICATION_CASES_INDEX = CLUSTER_CASES_INDEX
DEFAULT_TEMPLATES_DIR = AI_PIPELINE_ROOT / "templates"
DEFAULT_SECTION_CONCURRENCY = 0

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s*(.+)$")
_BULLET_LINE_RE = re.compile(r"^(-\s+)(.+)$")


def _normalize_heading_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    return normalized.encode("ascii", "ignore").decode("ascii")


def _heading_label(text: str) -> str:
    stripped = text.strip()
    return stripped if stripped.endswith(":") else f"{stripped}:"


def _demote_markdown_headings(lines: list[str]) -> list[str]:
    demoted: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        match = _HEADING_LINE_RE.match(line.strip())
        if not match:
            demoted.append(line)
            index += 1
            continue

        heading_text = match.group(2).strip()
        heading_label, separator, heading_body = heading_text.partition(":")
        if separator and heading_body.strip():
            demoted.append(heading_text)
            index += 1
            continue
        if separator:
            heading_text = _heading_label(heading_label)

        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1

        if next_index >= len(lines):
            index += 1
            continue

        next_line = lines[next_index].strip()
        if _HEADING_LINE_RE.match(next_line):
            index += 1
            continue

        bullet_match = _BULLET_LINE_RE.match(next_line)
        if bullet_match:
            demoted.append(
                f"{bullet_match.group(1)}{_heading_label(heading_text)} "
                f"{bullet_match.group(2).strip()}"
            )
        else:
            demoted.append(f"{_heading_label(heading_text)} {next_line}")
        index = next_index + 1
    return demoted


def normalize_section_generation_content(content: str, *, heading: str) -> str:
    normalized_heading = _normalize_heading_text(heading)
    lines = content.strip().splitlines()
    while lines:
        match = _HEADING_LINE_RE.match(lines[0].strip())
        if match and _normalize_heading_text(match.group(2)) == normalized_heading:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
            continue
        break
    return "\n".join(_demote_markdown_headings(lines)).strip()


def render_generated_section_markdown(content: str, *, heading: str) -> str | None:
    body = normalize_section_generation_content(content, heading=heading)
    if not body:
        return None
    return f"## {heading}\n\n{body}\n"


class GenerationValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        section_id: str,
        generation_route: str,
        generation_substep: str,
        section_heading: str | None = None,
        cluster_ids: list[str] | None = None,
        context_present: bool | None = None,
        context_chars: int | None = None,
        prompt_version: str | None = None,
        allowed_evidence_ids: list[str] | None = None,
        evidence_count: int | None = None,
        planner_items: list[dict[str, object]] | None = None,
        planned_items_block: str | None = None,
        planner_response: str | None = None,
        raw_response: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        super().__init__(message)
        self.section_id = section_id
        self.section_heading = section_heading
        self.generation_route = generation_route
        self.generation_substep = generation_substep
        self.cluster_ids = list(cluster_ids or [])
        self.context_present = context_present
        self.context_chars = context_chars
        self.prompt_version = prompt_version
        self.allowed_evidence_ids = (
            list(allowed_evidence_ids) if allowed_evidence_ids is not None else None
        )
        self.evidence_count = evidence_count
        self.planner_items = (
            list(planner_items) if planner_items is not None else None
        )
        self.planned_items_block = planned_items_block
        self.planner_response = planner_response
        self.raw_response = raw_response
        self.retry_count = retry_count

    def diagnostics(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "section_id": self.section_id,
            "generation_route": self.generation_route,
            "generation_substep": self.generation_substep,
        }
        if self.section_heading is not None:
            payload["section_heading"] = self.section_heading
        if self.cluster_ids:
            payload["cluster_ids"] = self.cluster_ids
        if self.context_present is not None:
            payload["context_present"] = self.context_present
        if self.context_chars is not None:
            payload["context_chars"] = self.context_chars
        if self.prompt_version is not None:
            payload["prompt_version"] = self.prompt_version
        if self.allowed_evidence_ids is not None:
            payload["allowed_evidence_ids"] = self.allowed_evidence_ids
        if self.evidence_count is not None:
            payload["evidence_count"] = self.evidence_count
        if self.planner_items is not None:
            payload["planner_items"] = self.planner_items
        if self.planned_items_block is not None:
            payload["planned_items_block"] = self.planned_items_block
        if self.planner_response is not None:
            payload["planner_response"] = self.planner_response
        if self.raw_response is not None:
            payload["raw_response"] = self.raw_response
        if self.retry_count is not None:
            payload["retry_count"] = self.retry_count
        return payload


class ClusterAssignmentInput(BaseModel):
    cluster_id: str
    section_ids: list[str] = Field(default_factory=list)


class SectionPlanPoint(BaseModel):
    text: str
    evidence: list[str] = Field(default_factory=list)


class SectionPlanResult(BaseModel):
    section_id: str
    points: list[SectionPlanPoint] = Field(default_factory=list)


class PlannerItem(BaseModel):
    text: str
    e: list[str] = Field(default_factory=list)


class PlannerItemsResult(BaseModel):
    items: list[PlannerItem] = Field(default_factory=list)


class SectionGenerationResult(BaseModel):
    section_id: str
    content: str = ""


class GenerationSessionResult(BaseModel):
    sections: list[SectionGenerationResult] = Field(default_factory=list)
    skipped_sections: list[dict[str, str]] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SectionGenerationJob:
    section_id: str
    section: TemplateSection
    clusters: list[ClusterCase]
    context: str = ""
    evidence_spans: list[dict[str, object]] = field(default_factory=list)
    transcript_constraints: list[Directive] = field(default_factory=list)

    @property
    def cluster_ids(self) -> list[str]:
        return [cluster.id for cluster in self.clusters]

    @property
    def context_present(self) -> bool:
        return bool(self.context.strip())

    @property
    def context_chars(self) -> int:
        return len(self.context)

    @property
    def has_linked_evidence(self) -> bool:
        return bool(self.evidence_spans)


@dataclass(frozen=True, slots=True)
class SectionGenerationPlan:
    jobs: list[SectionGenerationJob]
    skipped_sections: list[dict[str, str]]

    @property
    def job_count(self) -> int:
        return len(self.jobs)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_count": self.job_count,
            "section_ids": [job.section_id for job in self.jobs],
            "skipped_section_ids": [
                section["section_id"] for section in self.skipped_sections
            ],
        }


def load_classification_result(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("generation_classification_result_must_be_object")
    return payload


def load_classification_assignments(path: Path) -> list[ClusterAssignmentInput]:
    payload = load_classification_result(path)
    session_result = payload.get("classification_session_result")
    if not isinstance(session_result, dict):
        raise ValueError("generation_classification_session_result_missing")

    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("generation_classification_assignments_missing")

    assignments: list[ClusterAssignmentInput] = []
    for index, item in enumerate(assignments_raw):
        if not isinstance(item, dict):
            raise ValueError(f"generation_assignment_{index}_must_be_object")
        try:
            assignments.append(ClusterAssignmentInput.model_validate(item))
        except ValidationError as exc:
            raise ValueError(f"generation_assignment_{index}_invalid: {exc}") from exc
    return assignments


def template_id_from_classification_result(path: Path) -> str | None:
    payload = load_classification_result(path)
    template_id = payload.get("template_id")
    if isinstance(template_id, str) and template_id.strip():
        return template_id.strip()
    return None


def group_clusters_by_section(
    assignments: list[ClusterAssignmentInput],
    clusters_by_id: dict[str, ClusterCase],
    template: ClinicalTemplate,
) -> dict[str, list[ClusterCase]]:
    allowed_section_ids = template.section_id_set()
    grouped: dict[str, list[ClusterCase]] = {
        section_id: [] for section_id in allowed_section_ids
    }
    seen_per_section: dict[str, set[str]] = {
        section_id: set() for section_id in allowed_section_ids
    }

    for assignment in assignments:
        if assignment.cluster_id not in clusters_by_id:
            raise ValueError(
                f"generation_cluster_not_found: {assignment.cluster_id!r}"
            )
        cluster = clusters_by_id[assignment.cluster_id]
        for section_id in assignment.section_ids:
            if section_id not in allowed_section_ids:
                raise ValueError(f"generation_unknown_section_id: {section_id!r}")
            if assignment.cluster_id in seen_per_section[section_id]:
                continue
            grouped[section_id].append(cluster)
            seen_per_section[section_id].add(assignment.cluster_id)
    return grouped


def plan_section_generation(
    assignments: list[ClusterAssignmentInput],
    clusters_by_id: dict[str, ClusterCase],
    template: ClinicalTemplate,
    *,
    section_context: SectionContext | None = None,
    section_evidence: SectionEvidence | None = None,
    transcript_directives: list[Directive] | None = None,
) -> SectionGenerationPlan:
    grouped = group_clusters_by_section(assignments, clusters_by_id, template)
    context_map = section_context or {}
    evidence_map = section_evidence or {}
    directive_list = list(transcript_directives or [])
    jobs: list[SectionGenerationJob] = []
    skipped_sections: list[dict[str, str]] = []

    for section in template.sections:
        clusters = grouped.get(section.section_id, [])
        context = context_map.get(section.section_id, "")
        evidence_spans = list(evidence_map.get(section.section_id, []))
        constraints = transcript_directives_for_section(
            directive_list,
            section.section_id,
        )
        if clusters or context.strip():
            jobs.append(
                SectionGenerationJob(
                    section_id=section.section_id,
                    section=section,
                    clusters=clusters,
                    context=context,
                    evidence_spans=evidence_spans,
                    transcript_constraints=constraints,
                )
            )
            continue
        skipped_sections.append(
            {
                "section_id": section.section_id,
                "heading": section.heading,
            }
        )
    return SectionGenerationPlan(jobs=jobs, skipped_sections=skipped_sections)


def render_section_user_payload(
    *,
    section: TemplateSection,
    clusters: list[ClusterCase],
    context: str = "",
    template: ClinicalTemplate,
) -> str:
    if not clusters and not context.strip():
        raise ValueError(
            "generation_section_payload_requires_at_least_one_cluster_or_context"
        )
    payload = {
        "section": section.to_generation_payload(),
        "template_guidelines": template.generation.guidelines,
        "clusters": [cluster_to_payload_item(cluster) for cluster in clusters],
        "context": context,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def load_section_context_from_record(path: Path) -> SectionContext:
    payload = json.loads(path.read_text(encoding="utf-8"))
    section_context_raw = payload.get("section_context")
    if isinstance(section_context_raw, dict):
        section_context: SectionContext = {}
        for section_id, content in section_context_raw.items():
            if isinstance(section_id, str) and isinstance(content, str):
                section_context[section_id] = content
        if section_context:
            return section_context

    adapter_export = payload.get("section_adapter_result")
    if isinstance(adapter_export, dict):
        nested = adapter_export.get("section_context")
        if isinstance(nested, dict):
            section_context = {
                str(section_id): str(content)
                for section_id, content in nested.items()
                if isinstance(section_id, str) and isinstance(content, str)
            }
            if section_context:
                return section_context

    raise ValueError("generation_context_record_has_no_section_context")


def load_section_evidence_from_record(path: Path) -> SectionEvidence:
    payload = json.loads(path.read_text(encoding="utf-8"))
    section_evidence_raw = payload.get("section_evidence")
    if isinstance(section_evidence_raw, dict):
        return _normalize_section_evidence(section_evidence_raw)

    adapter_export = payload.get("section_adapter_result")
    if isinstance(adapter_export, dict):
        nested = adapter_export.get("section_evidence")
        if isinstance(nested, dict):
            return _normalize_section_evidence(nested)

    return {}


def _normalize_section_evidence(raw: dict[str, object]) -> SectionEvidence:
    evidence: SectionEvidence = {}
    for section_id, spans_raw in raw.items():
        if not isinstance(section_id, str) or not isinstance(spans_raw, list):
            continue
        spans: list[dict[str, object]] = []
        for item in spans_raw:
            if not isinstance(item, dict):
                continue
            span_id = item.get("id")
            doc = item.get("doc")
            text = item.get("text")
            if (
                not isinstance(span_id, str)
                or not isinstance(doc, str)
                or not isinstance(text, str)
            ):
                continue
            span_dict: dict[str, object] = {"id": span_id, "doc": doc, "text": text}
            date_hint = item.get("date_hint")
            if isinstance(date_hint, str) and date_hint.strip():
                span_dict["date_hint"] = date_hint.strip()
            spans.append(span_dict)
        if spans:
            evidence[section_id] = spans
    return evidence


_SPEAKER_ROLE_MAP = {
    "MEDICO": "doctor",
    "MÉDICO": "doctor",
    "DOCTOR": "doctor",
    "PACIENTE": "patient",
    "ACOMPANANTE": "companion",
    "ACOMPAÑANTE": "companion",
}


def _speaker_to_role_key(speaker: str) -> str:
    normalized = speaker.strip().upper()
    return _SPEAKER_ROLE_MAP.get(normalized, normalized.lower())


def _turn_to_compact_item(turn: dict[str, object]) -> dict[str, str]:
    role = _speaker_to_role_key(str(turn["speaker"]))
    return {role: str(turn["text"])}


def _turn_to_id_item(turn: dict[str, object]) -> dict[str, str]:
    role = _speaker_to_role_key(str(turn["speaker"]))
    return {"id": f"t{turn['turn_id']}", role: str(turn["text"])}


def clusters_to_conversation_groups(
    clusters: list[ClusterCase],
    *,
    include_turn_ids: bool = False,
) -> list[list[dict[str, str]]]:
    groups: list[list[dict[str, str]]] = []
    for cluster in clusters:
        turns = build_cluster_turns(cluster.cluster_json)
        if include_turn_ids:
            groups.append([_turn_to_id_item(turn) for turn in turns])
        else:
            groups.append([_turn_to_compact_item(turn) for turn in turns])
    return groups


def render_evidence_block(job: SectionGenerationJob) -> str:
    lines: list[str] = []
    turn_lines: list[str] = []
    for cluster in job.clusters:
        for turn in build_cluster_turns(cluster.cluster_json):
            role = _speaker_to_role_key(str(turn["speaker"]))
            turn_id = f"t{turn['turn_id']}"
            turn_lines.append(f"[{turn_id}] {role}: {turn['text']}")
    if turn_lines:
        lines.append("Consulta actual:")
        lines.extend(turn_lines)

    external_lines: list[str] = []
    for span in job.evidence_spans:
        span_id = span.get("id")
        text = span.get("text")
        doc = span.get("doc")
        if not isinstance(span_id, str) or not isinstance(text, str):
            continue
        prefix = f"{doc}: " if isinstance(doc, str) and doc.strip() else ""
        external_lines.append(f"[{span_id}] {prefix}{text}".strip())
    if job.context.strip():
        external_lines.append(f"[{CONTEXT_BRIEF_EVIDENCE_ID}] {job.context.strip()}")

    if external_lines:
        if lines:
            lines.append("")
        lines.append("Contexto externo aprobado:")
        lines.extend(external_lines)

    if not lines:
        return "(sin evidencia disponible)"
    return "\n".join(lines)


def _section_guidelines_text(section: TemplateSection) -> str:
    return compose_section_guidelines(
        section.generation.guidelines,
        section.include,
        section.boundaries,
    )


def should_use_two_step_generation(
    job: SectionGenerationJob,
    *,
    linked_evidence_two_step: bool = False,
) -> bool:
    _ = job
    return linked_evidence_two_step


def generation_direct_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version(PY_GENERATION_DIRECT_STEP, prompt_version)


def generation_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_GENERATION_PROMPT_VERSIONS


def generation_direct_output_schema(
    *,
    section_id: str,
    prompt_version: str,
) -> dict[str, object] | None:
    if not generation_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module(PY_GENERATION_DIRECT_STEP, prompt_version)
    return module.output_schema(section_id=section_id)


def generation_planner_output_schema(
    *,
    allowed_evidence_ids: list[str],
    prompt_version: str,
) -> dict[str, object] | None:
    if not generation_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module(PY_GENERATION_PLANNER_STEP, prompt_version)
    return module.output_schema(allowed_evidence_ids=allowed_evidence_ids)


def load_generation_direct_prompt(version: str) -> str:
    if generation_direct_uses_py_prompt(version):
        return py_system_prompt(PY_GENERATION_DIRECT_STEP, version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_generation_planner_prompt(version: str) -> str:
    return py_system_prompt(PY_GENERATION_PLANNER_STEP, version)


def load_generation_renderer_prompt(version: str) -> str:
    return py_system_prompt(PY_GENERATION_RENDERER_STEP, version)


def render_transcript_constraints_block(constraints: list[Directive]) -> str:
    if not constraints:
        return ""
    from common.prompt_blocks import render_block

    payload = [constraint.model_dump(mode="json") for constraint in constraints]
    return render_block(
        "transcript_constraints",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def render_planner_payload(
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    *,
    prompt_version: str,
) -> str:
    module = load_py_prompt_module(PY_GENERATION_PLANNER_STEP, prompt_version)
    return module.render_user_payload(
        section_id=job.section.section_id,
        section_description=job.section.description,
        section_guidelines=_section_guidelines_text(job.section),
        template_guidelines=template.generation.guidelines,
        evidence_block=render_evidence_block(job),
        transcript_constraints_block=render_transcript_constraints_block(
            job.transcript_constraints
        ),
    )


def render_renderer_payload(
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    *,
    prompt_version: str,
    planned_items_block: str,
) -> str:
    module = load_py_prompt_module(PY_GENERATION_RENDERER_STEP, prompt_version)
    return module.render_user_payload(
        section_name=job.section.heading,
        section_description=job.section.description,
        section_guidelines=_section_guidelines_text(job.section),
        generation_mode=resolve_generation_mode(job.section),
        template_guidelines=template.generation.guidelines,
        planned_items_block=planned_items_block,
    )


def audit_planner_item_evidence(
    items: list[PlannerItem],
    *,
    allowed_evidence_ids: set[str],
) -> None:
    for item in items:
        if not item.text.strip():
            raise ValueError("generation_planner_empty_item_text")
        if not item.e:
            raise ValueError("generation_planner_missing_evidence")
        for evidence_id in item.e:
            if evidence_id not in allowed_evidence_ids:
                raise ValueError(
                    f"generation_planner_unknown_evidence_id: {evidence_id!r}"
                )


def parse_planner_items_result(
    raw: str,
    *,
    allowed_evidence_ids: set[str],
) -> PlannerItemsResult:
    payload = extract_json_object(raw)
    try:
        result = PlannerItemsResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"generation_invalid_planner_items: {exc}") from exc
    audit_planner_item_evidence(result.items, allowed_evidence_ids=allowed_evidence_ids)
    return result


def render_planned_items_block(items: list[PlannerItem]) -> str:
    if not items:
        return "(sin items planificados)"
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        evidence = ",".join(item.e)
        lines.append(f"[{index}] {item.text.strip()} evidence: {evidence}")
    return "\n".join(lines)


def planner_items_to_export(items: list[PlannerItem]) -> list[dict[str, object]]:
    return [{"text": item.text, "e": list(item.e)} for item in items]


def parse_linked_content(raw: str) -> str:
    return parse_linked_plaintext(raw)


def generation_prompt_reference(version: str) -> str:
    if generation_direct_uses_py_prompt(version):
        module_path = load_py_prompt_module(PY_GENERATION_DIRECT_STEP, version).__name__
        return f"{module_path.replace('.', '/')}.py"
    return str(generation_prompt_file_path(version).relative_to(MODULE_ROOT))


def render_direct_payload(
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    *,
    prompt_version: str,
) -> str:
    module = load_py_prompt_module(PY_GENERATION_DIRECT_STEP, prompt_version)
    return module.render_user_payload(
        section_id=job.section.section_id,
        section_description=job.section.description,
        section_guidelines=_section_guidelines_text(job.section),
        template_guidelines=template.generation.guidelines,
        conversation_groups=clusters_to_conversation_groups(job.clusters),
        context_brief=job.context,
        transcript_constraints_block=render_transcript_constraints_block(
            job.transcript_constraints
        ),
    )


def load_transcript_directives_from_record(path: Path) -> list[Directive]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    triage_result = payload.get("triage_result")
    if not isinstance(triage_result, dict):
        return []
    directives_raw = triage_result.get("directives")
    if not isinstance(directives_raw, list):
        return []
    directives: list[Directive] = []
    for item in directives_raw:
        if isinstance(item, dict):
            directives.append(Directive.model_validate(item))
    return transcript_directives(directives)


def collect_allowed_evidence_ids(job: SectionGenerationJob) -> list[str]:
    allowed = sorted(collect_allowed_evidence_id_set(job))
    return allowed


def collect_allowed_evidence_id_set(job: SectionGenerationJob) -> set[str]:
    allowed: set[str] = set()
    for cluster in job.clusters:
        for turn in build_cluster_turns(cluster.cluster_json):
            allowed.add(f"t{turn['turn_id']}")
    for span in job.evidence_spans:
        span_id = span.get("id")
        if isinstance(span_id, str) and span_id.strip():
            allowed.add(span_id.strip())
    if job.context.strip():
        allowed.add(CONTEXT_BRIEF_EVIDENCE_ID)
    return allowed


def audit_plan_evidence(
    points: list[SectionPlanPoint],
    *,
    allowed_evidence_ids: set[str],
) -> None:
    for point in points:
        for evidence_id in point.evidence:
            if evidence_id not in allowed_evidence_ids:
                raise ValueError(
                    f"generation_plan_unknown_evidence_id: {evidence_id!r}"
                )


def parse_section_plan_result(
    raw: str,
    *,
    expected_section_id: str,
    allowed_evidence_ids: set[str],
) -> SectionPlanResult:
    payload = extract_json_object(raw)
    try:
        result = SectionPlanResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"generation_invalid_plan_result: {exc}") from exc
    if result.section_id != expected_section_id:
        raise ValueError(
            "generation_plan_section_id_mismatch: "
            f"expected {expected_section_id!r}, got {result.section_id!r}"
        )
    audit_plan_evidence(result.points, allowed_evidence_ids=allowed_evidence_ids)
    return result


def generation_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_generation_prompt(version: str) -> str:
    return load_generation_direct_prompt(version)


def prompt_file_path(version: str) -> Path:
    return generation_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_generation_prompt(version)


def parse_section_generation_result(
    raw: str,
    *,
    expected_section_id: str,
) -> SectionGenerationResult:
    payload = extract_json_object(raw)
    try:
        result = SectionGenerationResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"generation_invalid_section_result: {exc}") from exc
    if result.section_id != expected_section_id:
        raise ValueError(
            "generation_section_id_mismatch: "
            f"expected {expected_section_id!r}, got {result.section_id!r}"
        )
    return result


def format_two_step_llm_responses_for_export(
    llm_responses: list[object],
) -> list[dict[str, object]]:
    steps = ("planner", "renderer")
    labeled: list[dict[str, object]] = []
    for index, response in enumerate(llm_responses):
        content = getattr(response, "content", None)
        if not isinstance(content, str):
            continue
        usage = getattr(response, "usage", {})
        request_params = getattr(response, "request_params", {})
        step = steps[index] if index < len(steps) else f"call_{index}"
        labeled.append(
            {
                "step": step,
                "content": content,
                "usage": dict(usage) if isinstance(usage, dict) else {},
                "request_params": (
                    dict(request_params) if isinstance(request_params, dict) else {}
                ),
            }
        )
    return labeled


def enrich_section_generation_result_for_export(
    result: SectionGenerationResult,
    *,
    heading: str,
    cluster_ids: list[str],
    context_present: bool = False,
    context_chars: int = 0,
) -> dict[str, object]:
    return {
        "section_id": result.section_id,
        "heading": heading,
        "cluster_ids": list(cluster_ids),
        "context_present": context_present,
        "context_chars": context_chars,
        "content": result.content,
        "content_chars": len(result.content),
    }


def enrich_generation_session_result_for_export(
    result: GenerationSessionResult,
    template: ClinicalTemplate,
    *,
    cluster_ids_by_section: dict[str, list[str]],
    context_present_by_section: dict[str, bool] | None = None,
    context_chars_by_section: dict[str, int] | None = None,
) -> dict[str, object]:
    headings_by_id = template.headings_by_section_id()
    context_present_map = context_present_by_section or {}
    context_chars_map = context_chars_by_section or {}
    sections: list[dict[str, object]] = []
    for section_result in result.sections:
        sections.append(
            enrich_section_generation_result_for_export(
                section_result,
                heading=headings_by_id.get(
                    section_result.section_id,
                    section_result.section_id,
                ),
                cluster_ids=cluster_ids_by_section.get(section_result.section_id, []),
                context_present=context_present_map.get(
                    section_result.section_id,
                    False,
                ),
                context_chars=context_chars_map.get(section_result.section_id, 0),
            )
        )
    return {
        "sections": sections,
        "section_count": len(sections),
        "skipped_sections": list(result.skipped_sections),
        "skipped_section_count": len(result.skipped_sections),
    }


def format_section_output_for_detail(
    section_output: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return section_output

    compact_section: dict[str, object] = {}
    for key in (
        "section_id",
        "cluster_ids",
        "response_time_ms",
        "generation_result",
        "generation_route",
        "planner_items",
        "planned_items_block",
        "draft_with_evidence",
        "llm_responses",
        "thinking_source",
        "llm_usage",
        "llm_request_params",
    ):
        if key in section_output:
            compact_section[key] = section_output[key]

    thinking = section_output.get("thinking")
    if isinstance(thinking, str) and thinking:
        compact_section["thinking"] = thinking
        compact_section["thinking_chars"] = len(thinking)

    return compact_section


def format_generation_output_for_detail(
    output: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return output

    if "section_outputs" in output:
        compact_sections: list[dict[str, object]] = []
        for section_output in output["section_outputs"]:
            if not isinstance(section_output, dict):
                continue
            compact_sections.append(
                format_section_output_for_detail(section_output, output_detail)
            )
        output = {**output, "section_outputs": compact_sections}

    compact: dict[str, object] = {}
    for key in (
        "provider",
        "model",
        "generation_session_result",
        "section_plan",
        "section_outputs",
        "error",
    ):
        if key in output:
            compact[key] = output[key]
    return compact


def format_session_debug_output(
    result: GenerationSessionResult,
    template: ClinicalTemplate,
) -> str:
    headings_by_id = template.headings_by_section_id()
    lines: list[str] = []
    lines.append("generated sections:")
    for section_result in result.sections:
        heading = headings_by_id.get(
            section_result.section_id,
            section_result.section_id,
        )
        preview = section_result.content.strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        if not preview:
            preview = "(empty)"
        lines.append(f"  - {section_result.section_id} ({heading}): {preview}")
    if result.skipped_sections:
        lines.append("skipped sections:")
        for skipped in result.skipped_sections:
            lines.append(
                f"  - {skipped['section_id']} ({skipped.get('heading', '')})"
            )
    return "\n".join(lines)


__all__ = [
    "DEFAULT_CLASSIFICATION_CASES_INDEX",
    "DEFAULT_OUTPUT_DETAIL",
    "DEFAULT_PROMPT_VERSION",
    "DEFAULT_SECTION_CONCURRENCY",
    "DEFAULT_TEMPLATES_DIR",
    "MODULE_ROOT",
    "PY_GENERATION_DIRECT_STEP",
    "PY_GENERATION_PLANNER_STEP",
    "PY_GENERATION_RENDERER_STEP",
    "ClusterAssignmentInput",
    "GenerationSessionResult",
    "GenerationValidationError",
    "SectionGenerationJob",
    "SectionGenerationPlan",
    "SectionGenerationResult",
    "PlannerItem",
    "PlannerItemsResult",
    "SectionPlanPoint",
    "SectionPlanResult",
    "audit_planner_item_evidence",
    "audit_plan_evidence",
    "clusters_to_conversation_groups",
    "collect_allowed_evidence_id_set",
    "collect_allowed_evidence_ids",
    "enrich_generation_session_result_for_export",
    "enrich_section_generation_result_for_export",
    "format_generation_output_for_detail",
    "format_section_output_for_detail",
    "format_two_step_llm_responses_for_export",
    "format_session_debug_output",
    "generation_direct_output_schema",
    "generation_direct_uses_py_prompt",
    "generation_planner_output_schema",
    "generation_prompt_file_path",
    "generation_prompt_reference",
    "generation_structured_output_enabled",
    "load_generation_direct_prompt",
    "load_generation_planner_prompt",
    "load_generation_renderer_prompt",
    "load_section_evidence_from_record",
    "normalize_section_generation_content",
    "parse_linked_content",
    "parse_planner_items_result",
    "parse_section_generation_result",
    "parse_section_plan_result",
    "planner_items_to_export",
    "plan_section_generation",
    "prompt_file_path",
    "render_direct_payload",
    "render_evidence_block",
    "render_generated_section_markdown",
    "render_planned_items_block",
    "render_planner_payload",
    "render_renderer_payload",
    "render_section_user_payload",
    "should_use_two_step_generation",
    "template_id_from_classification_result",
    "load_classification_assignments",
    "load_section_context_from_record",
    "load_classification_result",
    "load_generation_prompt",
    "load_prompt",
]
