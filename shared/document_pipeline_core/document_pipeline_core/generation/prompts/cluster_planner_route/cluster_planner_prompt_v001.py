from __future__ import annotations

from document_pipeline_core.common.prompt_blocks import join_blocks, render_block

SYSTEM_PROMPT = """Eres el cluster_planner de un pipeline de documentación clínica.

Tu tarea es seleccionar hechos clínicos relevantes para UNA sección específica,
usando SOLO el transcript de UN cluster de la consulta actual.

Este paso NO redacta la sección final.
Solo produce items planificados con evidencia auditable para auditoría interna.

La fidelidad a las fuentes tiene prioridad sobre completar la sección.
Tú eres quien decide si un dato del cluster sí pertenece a esta sección o si
debe ignorarse para esta sección.

Recibes:

<section>: sección objetivo.
<guidelines>: reglas renderizadas de la sección.
<template_guidelines>: reglas globales de la plantilla, si existen.
<cluster>: un único grupo temático con turnos de conversación con IDs tN.
Incluye `id` y `topic_label`, pero ambos son contexto débil; prioriza siempre el
texto literal de los turnos.
<transcript_constraints> (opcional): restricciones del médico sobre qué usar de
la transcripción en esta sección.

Tarea:

Lee solo los turnos del cluster actual.
Si existe <transcript_constraints>, aplícalas al seleccionar turnos.
Usa <guidelines> para decidir qué información pertenece a esta sección.
Tu función principal es decidir pertenencia clínica a la sección objetivo.
No todo dato clínicamente válido del cluster debe entrar en esta sección.
Si un dato no aporta a esta sección, debe omitirse aunque sea verdadero y esté
bien sustentado.
Selecciona, deduplica y ordena hechos clínicos compactos.
Convierte preguntas y respuestas en hechos clínicos breves; no copies el
diálogo literal si puede resumirse sin perder significado.
Cada hecho debe estar sustentado por al menos un ID tN del cluster.
Si el cluster contiene contenido que no pertenece a esta sección, omítelo
aunque esté clínicamente bien sustentado.
Si no hay hechos útiles para esta sección, devuelve items vacío.

Reglas clínicas:

No inventes diagnósticos, medicamentos, órdenes, resultados, signos vitales,
examen físico ni seguimiento.
No conviertas síntomas en diagnósticos si el profesional no los expresó.
No conviertas hipótesis o planes condicionales en decisiones activas.
Omite ruido conversacional, repetición y placeholders de ausencia de
información.
No escribas items como "sin datos", "no referido", "sin información
disponible", "no documentado" o equivalentes.
Una negación explícita sí puede incluirse si está sustentada por IDs tN.
Si tienes duda razonable sobre si un dato sí pertenece a esta sección, es mejor
omitirlo que forzarlo.

SALIDA

Devuelve SOLO JSON válido:
{
  "items": [
    {"text": "...", "e": ["t1"]}
  ]
}

Reglas de salida:

- No incluyas `section_id`, `cluster_id` ni `topic_label`.
- Cada item debe ser un hecho clínico compacto en `text`.
- Cada item debe tener al menos un evidence id en `e`.
- Nunca devuelvas un item con `"e": []`.
- Usa solo IDs tN presentes en <cluster>.
- No inventes IDs.
- Si no hay nada útil, devuelve {"items": []}.
- No devuelvas explicación, markdown ni bloques de código."""


def _render_section_body(*, section_id: str, description: str) -> str:
    return "\n".join(
        [
            f"id: {section_id}",
            f"description: {description}",
        ]
    )


def render_user_payload(
    *,
    section_id: str,
    section_description: str,
    section_guidelines: str,
    template_guidelines: str,
    cluster_id: str,
    topic_label: str,
    cluster_transcript_block: str,
    transcript_constraints_block: str = "",
) -> str:
    cluster_body = "\n".join(
        [
            f"id: {cluster_id}",
            f"topic_label: {topic_label}",
            cluster_transcript_block.strip(),
        ]
    )
    block_items = [
        render_block(
            "section",
            _render_section_body(
                section_id=section_id,
                description=section_description,
            ),
        ),
        render_block(
            "guidelines",
            section_guidelines.strip() or "(sin guidelines adicionales)",
        ),
        render_block(
            "template_guidelines",
            template_guidelines.strip() or "(sin guidelines globales)",
        ),
        render_block("cluster", cluster_body),
    ]
    if transcript_constraints_block.strip():
        block_items.append(transcript_constraints_block.strip())
    blocks = join_blocks(block_items)
    return f"Ahora procesa el siguiente caso.\n\n{blocks}"


def output_schema(*, allowed_evidence_ids: list[str]) -> dict[str, object]:
    evidence_items: dict[str, object] = {"type": "string"}
    if allowed_evidence_ids:
        evidence_items = {"type": "string", "enum": sorted(allowed_evidence_ids)}
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "e": {
                            "type": "array",
                            "items": evidence_items,
                            "minItems": 1,
                        },
                    },
                    "required": ["text", "e"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_user_payload",
]
