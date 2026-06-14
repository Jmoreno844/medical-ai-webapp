from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import (
    ClassifyClustersResult,
    Span,
    SpanCluster,
    audit_classify_clusters,
    cluster_to_payload_item,
    span_to_payload_item,
)
from common.json_utils import extract_json_object
from common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_system_prompt
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path
from common.templates import ClinicalTemplate

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "classify_clusters"
PY_CLASSIFY_CLUSTERS_STEP = "context_classify_clusters"
PY_CLASSIFY_CLUSTERS_PROMPT_VERSIONS = frozenset({"v002"})


def classify_clusters_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version(PY_CLASSIFY_CLUSTERS_STEP, prompt_version)


def classify_clusters_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_CLASSIFY_CLUSTERS_PROMPT_VERSIONS


def classify_clusters_output_schema(
    *,
    template: ClinicalTemplate,
    clusters: list[SpanCluster],
    prompt_version: str,
) -> dict[str, object] | None:
    if not classify_clusters_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module(PY_CLASSIFY_CLUSTERS_STEP, prompt_version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(
            f"classify_clusters_py_prompt_missing_output_schema: {prompt_version}"
        )
    schema = output_schema_fn(
        cluster_ids=[cluster.id for cluster in clusters],
        section_ids=sorted(template.section_id_set()),
    )
    if not isinstance(schema, dict):
        raise ValueError(
            f"classify_clusters_py_prompt_invalid_output_schema: {prompt_version}"
        )
    return schema


def classify_clusters_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_classify_clusters_prompt(version: str) -> str:
    if classify_clusters_uses_py_prompt(version):
        return py_system_prompt(PY_CLASSIFY_CLUSTERS_STEP, version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def classify_clusters_prompt_reference(version: str) -> str:
    if classify_clusters_uses_py_prompt(version):
        module_path = load_py_prompt_module(PY_CLASSIFY_CLUSTERS_STEP, version).__name__
        return f"{module_path.replace('.', '/')}.py"
    return str(classify_clusters_prompt_file_path(version).relative_to(MODULE_ROOT))


def prompt_file_path(version: str) -> Path:
    return classify_clusters_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_classify_clusters_prompt(version)


def _template_sections_for_payload(
    template: ClinicalTemplate,
    *,
    prompt_version: str,
) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    if classify_clusters_uses_py_prompt(prompt_version):
        for section in template.sections:
            sections.append(section.to_classification_payload())
        return sections

    return [section.to_generation_payload() for section in template.sections]


def render_classify_clusters_payload(
    *,
    template: ClinicalTemplate,
    clusters: list[SpanCluster],
    spans: list[Span],
    encounter_date: str | None = None,
    document_date: str | None = None,
    prompt_version: str = "v001",
) -> str:
    if not clusters:
        raise ValueError("classify_clusters_payload_requires_at_least_one_cluster")
    template_sections = _template_sections_for_payload(
        template,
        prompt_version=prompt_version,
    )
    cluster_payload = [cluster_to_payload_item(cluster) for cluster in clusters]
    spans_payload = [span_to_payload_item(span) for span in spans]
    if classify_clusters_uses_py_prompt(prompt_version):
        module = load_py_prompt_module(PY_CLASSIFY_CLUSTERS_STEP, prompt_version)
        return module.render_user_payload(
            template_sections=template_sections,
            encounter_date=encounter_date,
            document_date=document_date,
            clusters=cluster_payload,
            spans=spans_payload,
        )
    payload = {
        "template_sections": template_sections,
        "encounter_date": encounter_date,
        "doc_date": document_date,
        "clusters": cluster_payload,
        "spans": spans_payload,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_classify_clusters_result(raw: str) -> ClassifyClustersResult:
    payload = extract_json_object(raw)
    try:
        return ClassifyClustersResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"classify_clusters_invalid_result: {exc}") from exc


def enrich_classify_clusters_result_for_export(
    result: ClassifyClustersResult,
    *,
    template: ClinicalTemplate,
) -> dict[str, object]:
    headings_by_id = template.headings_by_section_id()
    assignments: list[dict[str, object]] = []
    for assignment in result.assignments:
        assignments.append(
            {
                "cluster_id": assignment.cluster_id,
                "section_ids": assignment.section_ids,
                "section_headings": [
                    headings_by_id.get(section_id, section_id)
                    for section_id in assignment.section_ids
                ],
            }
        )
    return {
        "assignments": assignments,
        "assignment_count": len(assignments),
        "dropped_cluster_ids": result.dropped_cluster_ids(),
        "dropped_cluster_count": len(result.dropped_cluster_ids()),
    }


__all__ = [
    "MODULE_ROOT",
    "audit_classify_clusters",
    "classify_clusters_output_schema",
    "classify_clusters_prompt_file_path",
    "classify_clusters_prompt_reference",
    "classify_clusters_structured_output_enabled",
    "classify_clusters_uses_py_prompt",
    "enrich_classify_clusters_result_for_export",
    "load_classify_clusters_prompt",
    "load_prompt",
    "parse_classify_clusters_result",
    "prompt_file_path",
    "render_classify_clusters_payload",
]
