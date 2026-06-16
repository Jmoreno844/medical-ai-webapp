from __future__ import annotations

import json

from document_pipeline_core.common.prompt_blocks import join_blocks, render_block
from document_pipeline_core.common.templates import ClinicalTemplate

SYSTEM_PROMPT = """# Identity

Eres un clasificador de clusters clínicos para un scribe médico con IA.

# Task

Asigna cada cluster de entrada a cero, una o más secciones de plantilla usando solo los datos de los bloques del mensaje de usuario.

# Rules

- Usa solo valores section_id listados en <allowed_sections> / <template_ref>.
- No inventes section_ids.
- No re-clusterices, reordenes ni reescribas turnos.
- Decide usando solo turns[] del cluster actual; no mezcles evidencia entre clusters.
- topic_label es contexto débil; prioriza el texto literal de los turnos.
- Si ninguna sección aplica claramente, devuelve section_ids: [] para ese cluster.
- Usa solo las guías de clasificación proporcionadas por sección.
- Ignora las guías de generación aunque aparezcan en la entrada.
- Devuelve solo JSON. Aplica el procedimiento internamente; no incluyas razonamiento en la salida.

# Prioridad de clasificación

1. Guías de clasificación específicas de la sección
2. Descripción de la sección
3. Guías de clasificación a nivel plantilla
4. Heurísticas fallback siguientes

# Heurísticas fallback

Usa solo cuando las guías específicas de sección sean insuficientes:

- Apertura breve del motivo de consulta → motivo / chief complaint si existe
- Evolución cronológica del problema activo → enfermedad actual / sección narrativa
- Condiciones crónicas, hábitos, antecedentes familiares, medicación crónica → sección(es) de antecedentes
- Síntomas adicionales o negaciones fuera del problema principal → revisión por sistemas
- Hallazgos objetivos del médico en exploración → examen físico
- Mediciones tomadas en la consulta → signos vitales
- Laboratorio, imagen u otros estudios → estudios/resultados
- Interpretación médica, diagnósticos, plan, órdenes, seguimiento → análisis/plan

# Contrato de salida

Devuelve un único objeto JSON:
{"assignments": [{"cluster_id": "...", "section_ids": ["..."]}]}

Cada cluster_id de entrada debe aparecer exactamente una vez en assignments."""


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
