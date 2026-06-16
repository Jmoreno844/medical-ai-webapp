from __future__ import annotations

import json

from document_pipeline_core.common.prompt_blocks import join_blocks, render_block
from document_pipeline_core.common.templates import ClinicalTemplate

SYSTEM_PROMPT = """# Identity

You are a clinical cluster classifier for an AI medical scribe.

# Task

Assign each input cluster to zero, one, or more template sections using only the data in the user message blocks.

# Rules

- Use only section_id values listed in <allowed_sections> / <template_ref>.
- Do not invent section_ids.
- Do not re-cluster, reorder, or rewrite turns.
- Decide using only turns[] from the current cluster; do not mix evidence across clusters.
- topic_label is weak context; prefer literal turn text.
- If no section clearly applies, return section_ids: [] for that cluster.
- Use only classification guidelines provided per section.
- Ignore generation guidelines even if they appear in the input.
- Return JSON only. Apply the procedure internally; do not include reasoning in the output.

# Classification priority

1. Section-specific classification guidelines
2. Section description
3. Template-level classification guidelines
4. Fallback heuristics below

# Fallback heuristics

Use only when section-specific guidance is insufficient:

- Brief opening reason for visit → chief complaint / motivo section if present
- Chronological evolution of the active problem → current illness / narrative section
- Chronic conditions, habits, family history, chronic meds → antecedents section(s)
- Additional symptoms or negations outside the main problem → review of systems
- Objective physician findings on exam → physical exam
- Measurements taken during the encounter → vital signs
- Labs, imaging, or other study results → studies/results section
- Physician interpretation, diagnoses, plan, orders, follow-up → analysis/plan section

# Output contract

Return a single JSON object:
{"assignments": [{"cluster_id": "...", "section_ids": ["..."]}]}

Each input cluster_id must appear exactly once in assignments."""


def _render_template_ref(template: ClinicalTemplate) -> str:
    allowed_section_ids = sorted(template.section_id_set())
    return "\n".join(
        [
            f"id: {template.id}",
            f"allowed_section_ids: {json.dumps(allowed_section_ids, ensure_ascii=False)}",
        ]
    )


def _render_allowed_sections(template: ClinicalTemplate) -> str:
    section_blocks: list[str] = []
    for section in template.sections:
        classification_payload = section.to_classification_payload()
        guidelines = str(classification_payload.get("guidelines", "")).strip()
        lines = [
            f'<section id="{section.section_id}">',
            f"Title: {section.heading}",
            f"Description: {section.description}",
        ]
        if guidelines:
            lines.append(f"Classification guidelines: {guidelines}")
        lines.append("</section>")
        section_blocks.append("\n".join(lines))
    return "\n\n".join(section_blocks)


def render_template_context(*, template: ClinicalTemplate) -> str:
    global_guidelines = template.classification.guidelines.strip()
    blocks = [
        render_block("template_ref", _render_template_ref(template)),
    ]
    if global_guidelines:
        blocks.append(
            render_block("template_classification_guidelines", global_guidelines)
        )
    blocks.append(render_block("allowed_sections", _render_allowed_sections(template)))
    return join_blocks(blocks)


def render_user_payload(
    *,
    template: ClinicalTemplate,
    clusters: list[dict[str, object]],
) -> str:
    if not clusters:
        raise ValueError("classification_v004_payload_requires_at_least_one_cluster")
    blocks = [
        render_block("template_ref", _render_template_ref(template)),
    ]
    global_guidelines = template.classification.guidelines.strip()
    if global_guidelines:
        blocks.append(
            render_block("template_classification_guidelines", global_guidelines)
        )
    blocks.append(render_block("allowed_sections", _render_allowed_sections(template)))
    blocks.append(
        render_block(
            "clusters",
            json.dumps(clusters, ensure_ascii=False, indent=2),
        )
    )
    return join_blocks(blocks)


def output_schema(template: ClinicalTemplate) -> dict[str, object]:
    allowed_section_ids = sorted(template.section_id_set())
    return {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cluster_id": {"type": "string"},
                        "section_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": allowed_section_ids,
                            },
                        },
                    },
                    "required": ["cluster_id", "section_ids"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["assignments"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_template_context",
    "render_user_payload",
]
