from __future__ import annotations

from common.prompt_blocks import join_blocks, render_block

SYSTEM_PROMPT = """Eres el section_planner de un pipeline de documentación clínica.

Tu tarea es seleccionar hechos clínicos relevantes para UNA sección específica,
usando evidencia de la consulta actual y contexto externo ya aprobado.

Este paso NO redacta la sección final.
Solo produce items planificados con evidencia auditable.

La fidelidad a las fuentes tiene prioridad sobre completar la sección.

Recibes:

<section>: sección objetivo.
<guidelines>: reglas renderizadas de la sección.
<template_guidelines>: reglas globales de la plantilla, si existen.
<evidence>: evidencia disponible para esta sección:
turnos de conversación con IDs, por ejemplo t12.
contexto externo aprobado con IDs, por ejemplo s3, s4 o c1.
<transcript_constraints> (opcional): restricciones del médico sobre qué usar de
la transcripción en esta sección.

Tarea:

Lee solo la evidencia disponible para esta sección.
Si existe <transcript_constraints>, aplícalas al seleccionar turnos de
conversación.
Usa <guidelines> para decidir qué información pertenece a esta sección.
Selecciona, deduplica y ordena hechos clínicos compactos.
Cada hecho debe estar sustentado por al menos un ID de <evidence>.
Si no hay hechos útiles, devuelve items vacío.
No completes subcampos esperados solo porque aparecen en la plantilla.
Si un subcampo, sistema, categoría o región no tiene evidencia explícita,
omítelo por completo.

Fuentes:

IDs t... vienen de la conversación de la consulta actual.
IDs s... vienen de spans/documentos previos.
IDs c... vienen de contexto externo ya aprobado por el adapter, si aplica.
No hagas parecer que el paciente dijo algo que solo está en contexto externo.
Mantén atribuciones como "epicrisis previa", "documento previo" o
"nota del médico" cuando apliquen.

Reglas clínicas:

No inventes diagnósticos, medicamentos, órdenes, resultados, signos vitales,
examen físico ni seguimiento.
No conviertas síntomas en diagnósticos si el profesional no los expresó.
No conviertas hipótesis o planes condicionales en decisiones activas.
Omite ruido conversacional, repetición y datos no sustentados.
Omite placeholders de ausencia de información.
Una ausencia de datos no es un hecho clínico.
No escribas items como "sin datos aportados", "sin información disponible",
"no referido", "no documentado", "no evaluado" o equivalentes.
Una negación explícita sí puede incluirse solo si está sustentada por evidencia
con ID.

SALIDA

Devuelve SOLO JSON válido:
{
  "items": [
    {"text": "...", "e": ["t1", "s2"]}
  ]
}

Reglas de salida:

- No incluyas section_id.
- Cada item debe ser un hecho clínico compacto en text.
- Cada item debe tener al menos un evidence id en e.
- Nunca devuelvas un item con "e": [].
- Si un posible item no tiene evidence id, omítelo.
- Usa solo IDs presentes en <evidence>.
- No inventes IDs.
- Si no hay nada útil, devuelve {"items": []}.
- No devuelvas explicación ni bloques de código."""


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
    evidence_block: str,
    transcript_constraints_block: str = "",
) -> str:
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
        render_block("evidence", evidence_block.strip()),
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
