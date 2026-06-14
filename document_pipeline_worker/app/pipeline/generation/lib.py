from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from classification.lib import ClusterCase, cluster_to_payload_item
from common.case_paths import CLUSTER_CASES_INDEX
from common.context_claims import (
    ClaimAssignment,
    ClinicalClaim,
    claim_to_payload_item,
    group_claims_by_section,
)
from common.json_utils import extract_json_object
from common.output_detail import DEFAULT_OUTPUT_DETAIL
from common.prompts import (
    DEFAULT_PROMPT_VERSION,
)
from common.prompts import (
    load_prompt as load_prompt_from_file,
)
from common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)
from common.templates import ClinicalTemplate, TemplateSection

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "generation"
DEFAULT_CLASSIFICATION_CASES_INDEX = CLUSTER_CASES_INDEX
DEFAULT_TEMPLATES_DIR = AI_PIPELINE_ROOT / "templates"
DEFAULT_SECTION_CONCURRENCY = 0

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _normalize_heading_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    return normalized.encode("ascii", "ignore").decode("ascii")


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
    return "\n".join(lines).strip()


def render_generated_section_markdown(content: str, *, heading: str) -> str | None:
    body = normalize_section_generation_content(content, heading=heading)
    if not body:
        return None
    return f"## {heading}\n\n{body}\n"


class ClusterAssignmentInput(BaseModel):
    cluster_id: str
    section_ids: list[str] = Field(default_factory=list)


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
    enrichment_claims: list[ClinicalClaim]

    @property
    def cluster_ids(self) -> list[str]:
        return [cluster.id for cluster in self.clusters]

    @property
    def claim_ids(self) -> list[str]:
        return [claim.claim_id for claim in self.enrichment_claims]


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
    claim_assignments: list[ClaimAssignment] | None = None,
    claims_by_id: dict[str, ClinicalClaim] | None = None,
) -> SectionGenerationPlan:
    grouped = group_clusters_by_section(assignments, clusters_by_id, template)
    claims_grouped: dict[str, list[ClinicalClaim]] = {
        section_id: [] for section_id in template.section_id_set()
    }
    if claim_assignments is not None and claims_by_id is not None:
        claims_grouped = group_claims_by_section(
            claim_assignments,
            claims_by_id,
            template.section_id_set(),
        )
    jobs: list[SectionGenerationJob] = []
    skipped_sections: list[dict[str, str]] = []

    for section in template.sections:
        clusters = grouped.get(section.section_id, [])
        enrichment_claims = claims_grouped.get(section.section_id, [])
        if clusters or enrichment_claims:
            jobs.append(
                SectionGenerationJob(
                    section_id=section.section_id,
                    section=section,
                    clusters=clusters,
                    enrichment_claims=enrichment_claims,
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
    enrichment_claims: list[ClinicalClaim] | None = None,
    template: ClinicalTemplate,
) -> str:
    claims = enrichment_claims or []
    if not clusters and not claims:
        raise ValueError(
            "generation_section_payload_requires_at_least_one_cluster_or_claim"
        )
    payload = {
        "section": section.to_generation_payload(),
        "template_guidelines": template.generation.guidelines,
        "clusters": [cluster_to_payload_item(cluster) for cluster in clusters],
        "enrichment_claims": [claim_to_payload_item(claim) for claim in claims],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def load_claim_classification_assignments(path: Path) -> list[ClaimAssignment]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    session_result = payload.get("claim_classification_session_result")
    if not isinstance(session_result, dict):
        raise ValueError("generation_claim_classification_session_result_missing")
    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("generation_claim_classification_assignments_missing")
    assignments: list[ClaimAssignment] = []
    for index, item in enumerate(assignments_raw):
        if not isinstance(item, dict):
            raise ValueError(f"generation_claim_assignment_{index}_must_be_object")
        try:
            assignments.append(ClaimAssignment.model_validate(item))
        except ValidationError as exc:
            raise ValueError(
                f"generation_claim_assignment_{index}_invalid: {exc}"
            ) from exc
    return assignments


def load_claims_from_context_record(path: Path) -> list[ClinicalClaim]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    claims: list[ClinicalClaim] = []
    for key in ("decompose_result", "extract_result"):
        block = payload.get(key)
        if not isinstance(block, dict):
            continue
        claims_raw = block.get("claims")
        if not isinstance(claims_raw, list):
            continue
        for index, item in enumerate(claims_raw):
            if not isinstance(item, dict):
                raise ValueError(f"context_claim_{key}_{index}_must_be_object")
            claims.append(ClinicalClaim.model_validate(item))
    if not claims:
        raise ValueError("generation_context_record_has_no_claims")
    return claims


def load_claims_from_classification_record(
    path: Path,
) -> tuple[list[ClaimAssignment], dict[str, ClinicalClaim]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    claims_by_id: dict[str, ClinicalClaim] = {}
    claims_raw = payload.get("claims")
    if isinstance(claims_raw, list):
        for index, item in enumerate(claims_raw):
            if not isinstance(item, dict):
                raise ValueError(f"generation_context_claim_{index}_must_be_object")
            claim = ClinicalClaim.model_validate(item)
            claims_by_id[claim.claim_id] = claim
    assignments = load_claim_classification_assignments(path)
    if not claims_by_id:
        session_result = payload.get("claim_classification_session_result")
        if isinstance(session_result, dict):
            assignments_raw = session_result.get("assignments")
            if isinstance(assignments_raw, list):
                for index, item in enumerate(assignments_raw):
                    if not isinstance(item, dict):
                        continue
                    claim_id = item.get("claim_id")
                    claim_text = item.get("claim_text")
                    source_type = item.get("source_type")
                    claim_type = item.get("claim_type")
                    if (
                        isinstance(claim_id, str)
                        and isinstance(claim_text, str)
                        and isinstance(source_type, str)
                        and isinstance(claim_type, str)
                    ):
                        from common.context_claims import ClaimSourceType, ClaimType

                        claims_by_id[claim_id] = ClinicalClaim(
                            claim_id=claim_id,
                            text=claim_text,
                            source_type=ClaimSourceType(source_type),
                            claim_type=ClaimType(claim_type),
                        )
    if not claims_by_id:
        raise ValueError("generation_claim_classification_record_has_no_claims")
    return assignments, claims_by_id


def generation_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_generation_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


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


def enrich_section_generation_result_for_export(
    result: SectionGenerationResult,
    *,
    heading: str,
    cluster_ids: list[str],
    claim_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "section_id": result.section_id,
        "heading": heading,
        "cluster_ids": list(cluster_ids),
        "claim_ids": list(claim_ids or []),
        "content": result.content,
        "content_chars": len(result.content),
    }


def enrich_generation_session_result_for_export(
    result: GenerationSessionResult,
    template: ClinicalTemplate,
    *,
    cluster_ids_by_section: dict[str, list[str]],
    claim_ids_by_section: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    headings_by_id = template.headings_by_section_id()
    claim_ids_map = claim_ids_by_section or {}
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
                claim_ids=claim_ids_map.get(section_result.section_id, []),
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
    "ClusterAssignmentInput",
    "GenerationSessionResult",
    "SectionGenerationJob",
    "SectionGenerationPlan",
    "SectionGenerationResult",
    "enrich_generation_session_result_for_export",
    "enrich_section_generation_result_for_export",
    "format_generation_output_for_detail",
    "format_section_output_for_detail",
    "format_session_debug_output",
    "generation_prompt_file_path",
    "normalize_section_generation_content",
    "render_generated_section_markdown",
    "load_claim_classification_assignments",
    "load_claims_from_classification_record",
    "load_classification_assignments",
    "load_classification_result",
    "load_generation_prompt",
    "load_prompt",
    "parse_section_generation_result",
    "plan_section_generation",
    "prompt_file_path",
    "render_section_user_payload",
    "template_id_from_classification_result",
]
