from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import (
    ClassifyClustersResult,
    Span,
    SpanCluster,
    audit_classify_clusters,
    span_to_payload_item,
)
from common.json_utils import extract_json_object
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path
from common.templates import ClinicalTemplate

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "classify_clusters"


def classify_clusters_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_classify_clusters_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return classify_clusters_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_classify_clusters_prompt(version)


def render_classify_clusters_payload(
    *,
    template: ClinicalTemplate,
    clusters: list[SpanCluster],
    spans: list[Span],
) -> str:
    if not clusters:
        raise ValueError("classify_clusters_payload_requires_at_least_one_cluster")
    payload = {
        "template_sections": [
            section.to_generation_payload() for section in template.sections
        ],
        "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
        "spans": [span_to_payload_item(span) for span in spans],
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
    for cluster_id, section_ids in result.assignments.items():
        assignments.append(
            {
                "cluster_id": cluster_id,
                "section_ids": section_ids,
                "section_headings": [
                    headings_by_id.get(section_id, section_id)
                    for section_id in section_ids
                ],
            }
        )
    return {
        "assignments": assignments,
        "assignment_count": len(assignments),
    }


__all__ = [
    "MODULE_ROOT",
    "audit_classify_clusters",
    "enrich_classify_clusters_result_for_export",
    "load_classify_clusters_prompt",
    "load_prompt",
    "parse_classify_clusters_result",
    "prompt_file_path",
    "render_classify_clusters_payload",
]
