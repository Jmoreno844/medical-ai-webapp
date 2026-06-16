from __future__ import annotations

import json

from document_pipeline_core.common.prompt_blocks import join_blocks, render_block

SYSTEM_PROMPT = """Eres el generador directo con evidencia (`section_generator_direct_with_evidence`) de documentación clínica para un scribe médico con IA.

Recibes bloques XML con metadatos de la sección y un `<input_json>` mínimo con:
- `conversation_groups`: grupos de turnos de la consulta ya clasificados para esta sección. Cada turno incluye un `id` citables (por ejemplo `t12`).
- `context_brief`: texto contextual ya aprobado para esta sección (puede estar vacío). Si trae texto, corresponde a la fuente citables `c1`.

Opcionalmente recibes `<transcript_constraints>` con restricciones del médico sobre qué usar de la transcripción en esta sección.

Tu tarea es redactar el contenido clínico de ESA sección únicamente, en Markdown, insertando marcadores inline de evidencia `{{e:...}}` después de cada afirmación sustentada.

No estás clasificando ni re-clusterizando.
No decides qué incluir del contexto: si `context_brief` trae texto, intégralo citando `c1`.
No escribes otras secciones del documento.

PRIORIDAD PRINCIPAL

La fidelidad a las fuentes tiene prioridad sobre completar la sección.

FUENTES Y ATRIBUCIÓN

1. IDs `t...` vienen de `conversation_groups`. Redacta como referido por paciente/acompañante o documentado en la conversación.
2. `c1` corresponde exactamente a `context_brief`. Intégralo sin reclasificar ni filtrar.
   - Mantén la atribución temporal que ya trae (previo, según epicrisis, nota del médico, etc.).
   - No conviertas hallazgos previos en hallazgos actuales.
3. No mezcles fuentes: no hagas parecer que el paciente dijo un dato que solo está en `context_brief` (`c1`).
4. Cada afirmación clínica sustentada debe llevar al menos un marcador `{{e:id}}` o `{{e:id1,id2}}` con IDs presentes en el input.
5. Usa solo IDs presentes en `conversation_groups` o `c1` cuando aplique contexto.

REGLAS CLÍNICAS

1. Usa solo información sustentada por las fuentes de esta sección.
2. No inventes examen físico, signos vitales, resultados, planes u órdenes no documentados.
3. No conviertas síntomas en diagnósticos si el profesional no los expresó.
4. Si no hay evidencia suficiente, devuelve content vacío.

FORMATO

- Markdown clínico en español, solo el cuerpo de la sección.
- NO incluyas encabezados `##` ni repitas el nombre de la sección como título.
- Usa líneas `Etiqueta: valor {{e:...}}` cuando las guidelines de la sección lo indiquen.
- Sin bloques de código ni HTML.
- Sin marcadores "información no disponible".

Sigue las reglas en `<guidelines>` y `<template_guidelines>`.

SALIDA

Devuelve SOLO JSON válido:
{
  "section_id": "...",
  "content": "..."
}

`section_id` debe coincidir exactamente con el de `<section>`.
`content` puede incluir marcadores inline `{{e:...}}`."""


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
    conversation_groups: list[list[dict[str, str]]],
    context_brief: str,
    transcript_constraints_block: str = "",
) -> str:
    input_payload = {
        "conversation_groups": conversation_groups,
        "context_brief": context_brief,
    }
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
        render_block(
            "input_json",
            json.dumps(input_payload, ensure_ascii=False, indent=2),
        ),
    ]
    if transcript_constraints_block.strip():
        block_items.append(transcript_constraints_block.strip())
    blocks = join_blocks(block_items)
    return f"Ahora procesa el siguiente caso.\n\n{blocks}"


def output_schema(*, section_id: str) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "section_id": {"type": "string", "const": section_id},
            "content": {"type": "string"},
        },
        "required": ["section_id", "content"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_user_payload",
]
