from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

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
from common.case_paths import CLUSTER_CASES_INDEX
from common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_system_prompt
from common.templates import ClinicalTemplate as ClassificationTemplate
from common.templates import compose_section_guidelines

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "classification"
DEFAULT_CASES_INDEX = CLUSTER_CASES_INDEX
DEFAULT_TEMPLATES_DIR = AI_PIPELINE_ROOT / "templates"


@dataclass(frozen=True, slots=True)
class ClusterCase:
    id: str
    cluster_json: dict[str, object]
    template_id: str
    notes: str | None = None


class ClassificationResult(BaseModel):
    section_ids: list[str] = Field(default_factory=list)


class ClusterAssignment(BaseModel):
    cluster_id: str
    section_ids: list[str] = Field(default_factory=list)


class ClassificationBatchResult(BaseModel):
    assignments: list[ClusterAssignment] = Field(default_factory=list)


class ClassificationSessionResult(BaseModel):
    assignments: list[ClusterAssignment] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BatchAssignmentAudit:
    expected_cluster_ids: list[str]
    assigned_cluster_ids: list[str]
    missing_cluster_ids: list[str]
    extra_cluster_ids: list[str]
    duplicate_cluster_ids: list[str]
    invalid_section_cluster_ids: list[str]
    invalid_section_assignments: list[dict[str, object]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return (
            not self.missing_cluster_ids
            and not self.extra_cluster_ids
            and not self.duplicate_cluster_ids
            and not self.invalid_section_cluster_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "expected_cluster_count": len(self.expected_cluster_ids),
            "assigned_cluster_count": len(self.assigned_cluster_ids),
            "missing_cluster_ids": self.missing_cluster_ids,
            "extra_cluster_ids": self.extra_cluster_ids,
            "duplicate_cluster_ids": self.duplicate_cluster_ids,
            "invalid_section_cluster_ids": self.invalid_section_cluster_ids,
            "invalid_section_assignments": self.invalid_section_assignments,
        }


class ClassificationValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        raw_response: str | None = None,
        classification_result: dict[str, object] | None = None,
        batch_assignment_audit: dict[str, object] | None = None,
        cluster_ids: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.classification_result = classification_result
        self.batch_assignment_audit = batch_assignment_audit
        self.cluster_ids = list(cluster_ids or [])

    def diagnostics(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.raw_response is not None:
            payload["raw_response"] = self.raw_response
        if self.classification_result is not None:
            payload["classification_result"] = self.classification_result
        if self.batch_assignment_audit is not None:
            payload["batch_assignment_audit"] = self.batch_assignment_audit
        if self.cluster_ids:
            payload["cluster_ids"] = self.cluster_ids
        return payload


@dataclass(frozen=True, slots=True)
class SectionAudit:
    allowed_section_ids: list[str]
    assigned_section_ids: list[str]
    unknown_section_ids: list[str]
    duplicate_section_ids: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.unknown_section_ids and not self.duplicate_section_ids

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "allowed_section_count": len(self.allowed_section_ids),
            "assigned_section_count": len(set(self.assigned_section_ids)),
            "unknown_section_ids": self.unknown_section_ids,
            "duplicate_section_ids": self.duplicate_section_ids,
        }


def load_cluster_cases(index_path: Path) -> list[ClusterCase]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("classification_cases_index_must_be_a_list")

    cases_root = index_path.parent
    cases: list[ClusterCase] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"classification_case_{index}_must_be_an_object")
        case_id = item.get("id")
        notes = item.get("notes")
        template_id = item.get("template_id")
        cluster_json = item.get("cluster_json")
        cluster_file = item.get("cluster_file")

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"classification_case_{index}_id_must_be_non_empty")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError(f"classification_case_{index}_template_id_required")
        if notes is not None and not isinstance(notes, str):
            raise ValueError(f"classification_case_{index}_notes_must_be_str")
        if cluster_json is not None and cluster_file is not None:
            raise ValueError(
                f"classification_case_{index}_must_use_cluster_json_or_file"
            )
        if cluster_json is None and cluster_file is None:
            raise ValueError(f"classification_case_{index}_missing_cluster_source")

        if isinstance(cluster_file, str):
            cluster_path = cases_root / cluster_file
            cluster_payload = json.loads(cluster_path.read_text(encoding="utf-8"))
        else:
            cluster_payload = cluster_json

        if not isinstance(cluster_payload, dict):
            raise ValueError(f"classification_case_{index}_cluster_must_be_object")
        cases.append(
            ClusterCase(
                id=case_id.strip(),
                cluster_json=cluster_payload,
                template_id=template_id.strip(),
                notes=notes.strip() if isinstance(notes, str) else None,
            )
        )
    return cases


def select_cluster_cases(
    cases: list[ClusterCase],
    *,
    count: int | None = None,
    last: int | None = None,
    case_id: str | None = None,
) -> list[ClusterCase]:
    selected = cases
    if case_id:
        selected = [case for case in selected if case.id == case_id]
    if count is not None:
        selected = selected[:count]
    if last is not None:
        selected = selected[-last:]
    if case_id and not selected:
        raise ValueError(f"classification_case_not_found: {case_id}")
    return selected


def load_session_clusters(
    index_path: Path,
    session_id: str,
) -> list[ClusterCase]:
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ValueError("classification_session_id_must_be_non_empty")
    prefix = f"{normalized_session_id}_"
    clusters = [
        case
        for case in load_cluster_cases(index_path)
        if case.id.startswith(prefix)
    ]
    if not clusters:
        raise ValueError(f"classification_session_not_found: {normalized_session_id}")
    return sorted(clusters, key=lambda case: case.id)


def build_cluster_turns(cluster_json: dict[str, object]) -> list[dict[str, object]]:
    turns = cluster_json.get("turns")
    if not isinstance(turns, list):
        raise ValueError("classification_cluster_turns_must_be_a_list")
    catalog: list[dict[str, object]] = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise ValueError(f"classification_cluster_turn_{index}_must_be_object")
        speaker = turn.get("speaker")
        text = turn.get("text")
        turn_id = turn.get("turn_id")
        if not isinstance(speaker, str) or not isinstance(text, str):
            raise ValueError(f"classification_cluster_turn_{index}_missing_fields")
        if not isinstance(turn_id, int):
            raise ValueError(f"classification_cluster_turn_{index}_turn_id_must_be_int")
        catalog.append(
            {
                "turn_id": turn_id,
                "speaker": speaker,
                "text": text,
            }
        )
    return catalog


def cluster_to_payload_item(cluster_case: ClusterCase) -> dict[str, object]:
    cluster_json = cluster_case.cluster_json
    topic_label = cluster_json.get("topic_label")
    if not isinstance(topic_label, str) or not topic_label.strip():
        raise ValueError("classification_cluster_topic_label_required")
    return {
        "cluster_id": cluster_case.id,
        "topic_label": topic_label.strip(),
        "turns": build_cluster_turns(cluster_json),
    }


def template_ref_for_classification_user(
    template: ClassificationTemplate,
) -> dict[str, object]:
    return {
        "id": template.id,
        "allowed_section_ids": sorted(template.section_id_set()),
    }


def format_template_for_classification_system(
    template: ClassificationTemplate,
) -> str:
    lines = [
        "PLANTILLA ACTIVA",
        f"id: {template.id}",
        f"name: {template.name}",
        f"document_kind: {template.document_kind}",
    ]
    global_guidelines = template.classification.guidelines.strip()
    if global_guidelines:
        lines.extend(
            [
                "",
                "Guías globales de clasificación:",
                global_guidelines,
            ]
        )
    lines.extend(
        [
            "",
            "Secciones permitidas (usa solo estos section_id):",
        ]
    )
    for section in template.sections:
        lines.append("")
        lines.append(f"### {section.section_id}")
        lines.append(f"heading: {section.heading}")
        lines.append(f"description: {section.description}")
        section_guidelines = compose_section_guidelines(
            section.classification.guidelines,
            section.include,
            section.boundaries,
        ).strip()
        if section_guidelines:
            lines.append(f"classification_guidelines: {section_guidelines}")
    return "\n".join(lines)


def build_classification_system_prompt(
    base_system_prompt: str,
    template: ClassificationTemplate,
) -> str:
    template_block = format_template_for_classification_system(template)
    return f"{base_system_prompt.rstrip()}\n\n{template_block}"


ENRICHED_CLASSIFICATION_PROMPT_VERSIONS = frozenset({"v003"})
PY_CLASSIFICATION_PROMPT_VERSIONS = frozenset({"v004"})


def classification_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version("classification", prompt_version)


def classification_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_CLASSIFICATION_PROMPT_VERSIONS


def classification_uses_enriched_system_prompt(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in ENRICHED_CLASSIFICATION_PROMPT_VERSIONS


def classification_output_schema(
    template: ClassificationTemplate,
    *,
    prompt_version: str,
) -> dict[str, object] | None:
    if not classification_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module("classification", prompt_version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(
            f"classification_py_prompt_missing_output_schema: {prompt_version}"
        )
    schema = output_schema_fn(template)
    if not isinstance(schema, dict):
        raise ValueError(f"classification_py_prompt_invalid_output_schema: {prompt_version}")
    return schema


def prepare_classification_prompts(
    base_system_prompt: str,
    template: ClassificationTemplate,
    *,
    prompt_version: str,
) -> tuple[str, bool]:
    if classification_uses_enriched_system_prompt(prompt_version):
        return (
            build_classification_system_prompt(base_system_prompt, template),
            True,
        )
    return base_system_prompt, False


def render_classification_user_payload(
    *,
    cluster_case: ClusterCase,
    template: ClassificationTemplate,
    prompt_version: str = "v002",
) -> str:
    if classification_uses_py_prompt(prompt_version):
        module = load_py_prompt_module("classification", prompt_version)
        return module.render_user_payload(
            template=template,
            clusters=[cluster_to_payload_item(cluster_case)],
        )
    cluster_json = cluster_case.cluster_json
    topic_label = cluster_json.get("topic_label")
    if not isinstance(topic_label, str) or not topic_label.strip():
        raise ValueError("classification_cluster_topic_label_required")
    template_payload: dict[str, object]
    if classification_uses_enriched_system_prompt(prompt_version):
        template_payload = {
            "template_ref": template_ref_for_classification_user(template),
        }
    else:
        template_payload = {"template": template.to_prompt_payload()}
    payload = {
        "cluster": {
            "topic_label": topic_label.strip(),
            "turns": build_cluster_turns(cluster_json),
        },
        **template_payload,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_classification_batch_payload(
    *,
    clusters: list[ClusterCase],
    template: ClassificationTemplate,
    prompt_version: str = "v002",
) -> str:
    if not clusters:
        raise ValueError("classification_batch_payload_requires_at_least_one_cluster")
    if classification_uses_py_prompt(prompt_version):
        module = load_py_prompt_module("classification", prompt_version)
        clusters_payload = [cluster_to_payload_item(cluster) for cluster in clusters]
        return module.render_user_payload(
            template=template,
            clusters=clusters_payload,
        )
    template_payload: dict[str, object]
    if classification_uses_enriched_system_prompt(prompt_version):
        template_payload = {
            "template_ref": template_ref_for_classification_user(template),
        }
    else:
        template_payload = {"template": template.to_prompt_payload()}
    payload = {
        "clusters": [cluster_to_payload_item(cluster) for cluster in clusters],
        **template_payload,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def classification_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_classification_prompt(version: str) -> str:
    if classification_uses_py_prompt(version):
        return py_system_prompt("classification", version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return classification_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_classification_prompt(version)


def parse_classification_result(raw: str) -> ClassificationResult:
    payload = extract_json_object(raw)
    try:
        return ClassificationResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"classification_invalid_result: {exc}") from exc


def parse_classification_batch_result(raw: str) -> ClassificationBatchResult:
    payload = extract_json_object(raw)
    try:
        return ClassificationBatchResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"classification_invalid_batch_result: {exc}") from exc


def audit_section_ids(
    result: ClassificationResult,
    template: ClassificationTemplate,
) -> SectionAudit:
    allowed_section_ids = sorted(template.section_id_set())
    allowed_set = template.section_id_set()
    assigned_section_ids = result.section_ids

    seen: set[str] = set()
    duplicate_section_ids: list[str] = []
    for section_id in assigned_section_ids:
        if section_id in seen and section_id not in duplicate_section_ids:
            duplicate_section_ids.append(section_id)
        seen.add(section_id)

    unknown_section_ids = sorted(
        {
            section_id
            for section_id in assigned_section_ids
            if section_id not in allowed_set
        }
    )
    return SectionAudit(
        allowed_section_ids=allowed_section_ids,
        assigned_section_ids=assigned_section_ids,
        unknown_section_ids=unknown_section_ids,
        duplicate_section_ids=sorted(duplicate_section_ids),
    )


def audit_batch_assignments(
    result: ClassificationBatchResult,
    expected_cluster_ids: list[str],
    template: ClassificationTemplate,
) -> BatchAssignmentAudit:
    assigned_cluster_ids = [assignment.cluster_id for assignment in result.assignments]
    expected_set = set(expected_cluster_ids)
    assigned_set = set(assigned_cluster_ids)

    seen: set[str] = set()
    duplicate_cluster_ids: list[str] = []
    for cluster_id in assigned_cluster_ids:
        if cluster_id in seen and cluster_id not in duplicate_cluster_ids:
            duplicate_cluster_ids.append(cluster_id)
        seen.add(cluster_id)

    missing_cluster_ids = sorted(expected_set - assigned_set)
    extra_cluster_ids = sorted(assigned_set - expected_set)

    invalid_section_cluster_ids: list[str] = []
    invalid_section_assignments: list[dict[str, object]] = []
    for assignment in result.assignments:
        section_audit = audit_section_ids(
            ClassificationResult(section_ids=assignment.section_ids),
            template,
        )
        if not section_audit.is_valid:
            invalid_section_cluster_ids.append(assignment.cluster_id)
            invalid_section_assignments.append(
                {
                    "cluster_id": assignment.cluster_id,
                    "assigned_section_ids": list(assignment.section_ids),
                    "unknown_section_ids": list(section_audit.unknown_section_ids),
                    "duplicate_section_ids": list(section_audit.duplicate_section_ids),
                }
            )

    return BatchAssignmentAudit(
        expected_cluster_ids=expected_cluster_ids,
        assigned_cluster_ids=assigned_cluster_ids,
        missing_cluster_ids=missing_cluster_ids,
        extra_cluster_ids=extra_cluster_ids,
        duplicate_cluster_ids=sorted(duplicate_cluster_ids),
        invalid_section_cluster_ids=sorted(invalid_section_cluster_ids),
        invalid_section_assignments=invalid_section_assignments,
    )


def merge_batch_results(
    batch_results: list[ClassificationBatchResult],
) -> ClassificationSessionResult:
    assignments: list[ClusterAssignment] = []
    for result in batch_results:
        assignments.extend(result.assignments)
    return ClassificationSessionResult(assignments=assignments)


def audit_session_result(
    result: ClassificationSessionResult,
    expected_cluster_ids: list[str],
    template: ClassificationTemplate,
) -> BatchAssignmentAudit:
    return audit_batch_assignments(
        ClassificationBatchResult(assignments=result.assignments),
        expected_cluster_ids,
        template,
    )


def enrich_classification_batch_result_for_export(
    result: ClassificationBatchResult,
    template: ClassificationTemplate,
) -> dict[str, object]:
    del template
    assignments: list[dict[str, object]] = []
    for assignment in result.assignments:
        assignments.append(
            {
                "cluster_id": assignment.cluster_id,
                "section_ids": list(assignment.section_ids),
            }
        )
    return {
        "assignments": assignments,
        "assignment_count": len(assignments),
    }


def enrich_classification_session_result_for_export(
    result: ClassificationSessionResult,
    template: ClassificationTemplate,
) -> dict[str, object]:
    return enrich_classification_batch_result_for_export(
        ClassificationBatchResult(assignments=result.assignments),
        template,
    )


def enrich_classification_result_for_export(
    result: ClassificationResult,
    template: ClassificationTemplate,
) -> dict[str, object]:
    del template
    return {
        "section_ids": list(result.section_ids),
        "section_count": len(result.section_ids),
    }


def format_classification_batch_output_for_detail(
    batch_output: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return batch_output

    compact_batch: dict[str, object] = {}
    for key in (
        "batch_index",
        "cluster_ids",
        "response_time_ms",
        "classification_result",
        "batch_assignment_audit",
        "thinking_source",
        "llm_usage",
        "llm_request_params",
    ):
        if key in batch_output:
            compact_batch[key] = batch_output[key]

    thinking = batch_output.get("thinking")
    if isinstance(thinking, str) and thinking:
        compact_batch["thinking_chars"] = len(thinking)

    return compact_batch


def format_classification_output_for_detail(
    output: dict[str, object],
    output_detail: str,
) -> dict[str, object]:
    from common.output_detail import normalize_output_detail

    if normalize_output_detail(output_detail) == "full":
        return output

    if "batch_outputs" in output:
        compact_batches: list[dict[str, object]] = []
        for batch in output["batch_outputs"]:
            if not isinstance(batch, dict):
                continue
            compact_batches.append(
                format_classification_batch_output_for_detail(batch, output_detail)
            )
        output = {**output, "batch_outputs": compact_batches}

    compact: dict[str, object] = {}
    for key in (
        "model_alias",
        "provider",
        "model",
        "classification_result",
        "classification_session_result",
        "batch_plan",
        "batch_assignment_audit",
        "batch_outputs",
        "section_audit",
        "error",
    ):
        if key in output:
            compact[key] = output[key]
    return compact


def format_section_audit(audit: SectionAudit) -> str:
    lines: list[str] = []
    if not audit.is_valid:
        lines.append("WARNING: invalid section_ids")
    lines.append("section audit:")
    lines.append(f"  allowed sections: {len(audit.allowed_section_ids)}")
    lines.append(f"  assigned: {audit.assigned_section_ids or '(none)'}")
    if audit.unknown_section_ids:
        lines.append(f"  unknown: {audit.unknown_section_ids}")
    if audit.duplicate_section_ids:
        lines.append(f"  duplicates: {audit.duplicate_section_ids}")
    if audit.is_valid:
        lines.append("  status: valid")
    return "\n".join(lines)


def format_batch_assignment_audit(audit: BatchAssignmentAudit) -> str:
    lines: list[str] = []
    if not audit.is_valid:
        lines.append("WARNING: invalid batch assignments")
    lines.append("batch assignment audit:")
    lines.append(f"  expected clusters: {len(audit.expected_cluster_ids)}")
    lines.append(f"  assigned clusters: {len(set(audit.assigned_cluster_ids))}")
    if audit.missing_cluster_ids:
        lines.append(f"  missing: {audit.missing_cluster_ids}")
    if audit.extra_cluster_ids:
        lines.append(f"  extra: {audit.extra_cluster_ids}")
    if audit.duplicate_cluster_ids:
        lines.append(f"  duplicates: {audit.duplicate_cluster_ids}")
    if audit.invalid_section_cluster_ids:
        lines.append(
            f"  invalid section_ids: {audit.invalid_section_cluster_ids}"
        )
    if audit.is_valid:
        lines.append("  status: valid")
    return "\n".join(lines)


def format_session_debug_output(
    result: ClassificationSessionResult,
    template: ClassificationTemplate,
) -> str:
    headings_by_id = template.headings_by_section_id()
    lines: list[str] = []
    lines.append("session assignments:")
    for assignment in result.assignments:
        section_labels = [
            f"{section_id} ({headings_by_id.get(section_id, section_id)})"
            for section_id in assignment.section_ids
        ]
        sections_text = ", ".join(section_labels) if section_labels else "(none)"
        lines.append(f"  - {assignment.cluster_id}: {sections_text}")
    return "\n".join(lines)


def format_debug_output(
    result: ClassificationResult,
    template: ClassificationTemplate,
    cluster_case: ClusterCase,
) -> str:
    headings_by_id = template.headings_by_section_id()
    topic_label = cluster_case.cluster_json.get("topic_label", "")
    turns = build_cluster_turns(cluster_case.cluster_json)
    lines: list[str] = []
    lines.append(f"cluster: {topic_label}")
    lines.append(f"turns: {len(turns)}")
    lines.append("assigned sections:")
    if not result.section_ids:
        lines.append("  (none)")
    else:
        for section_id in result.section_ids:
            heading = headings_by_id.get(section_id, section_id)
            lines.append(f"  - {section_id} ({heading})")
    lines.append("")
    lines.append("cluster turns:")
    for turn in turns:
        preview = str(turn["text"])
        if len(preview) > 100:
            preview = preview[:97] + "..."
        lines.append(f"  - {turn['turn_id']} ({turn['speaker']}): {preview}")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_CASES_INDEX",
    "DEFAULT_OUTPUT_DETAIL",
    "DEFAULT_PROMPT_VERSION",
    "DEFAULT_TEMPLATES_DIR",
    "MODULE_ROOT",
    "BatchAssignmentAudit",
    "ClassificationBatchResult",
    "ClassificationResult",
    "ClassificationSessionResult",
    "ClassificationValidationError",
    "ClusterAssignment",
    "ClusterCase",
    "SectionAudit",
    "build_classification_system_prompt",
    "classification_output_schema",
    "classification_structured_output_enabled",
    "classification_uses_enriched_system_prompt",
    "classification_uses_py_prompt",
    "format_template_for_classification_system",
    "prepare_classification_prompts",
    "template_ref_for_classification_user",
    "audit_batch_assignments",
    "audit_section_ids",
    "audit_session_result",
    "build_cluster_turns",
    "cluster_to_payload_item",
    "enrich_classification_batch_result_for_export",
    "enrich_classification_result_for_export",
    "enrich_classification_session_result_for_export",
    "format_batch_assignment_audit",
    "format_classification_batch_output_for_detail",
    "format_classification_output_for_detail",
    "format_debug_output",
    "format_section_audit",
    "format_session_debug_output",
    "load_cluster_cases",
    "load_prompt",
    "load_session_clusters",
    "merge_batch_results",
    "parse_classification_batch_result",
    "parse_classification_result",
    "prompt_file_path",
    "render_classification_batch_payload",
    "render_classification_user_payload",
    "select_cluster_cases",
]
