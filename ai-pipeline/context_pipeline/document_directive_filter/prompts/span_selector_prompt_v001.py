from __future__ import annotations

import json

from common.prompt_blocks import render_block

SYSTEM_PROMPT = """Eres el span_selector del pipeline clínico de contexto externo.

Tu tarea es elegir qué spans conservar según una directiva documental explícita del médico.

Recibes:
- `directive`: acción `limit_source_to` o `exclude_topic`, con `target`, `topic` e instrucción opcional.
- `spans[]`: spans candidatos del documento objetivo. Cada span tiene `id`, `doc`, `kind`, `text`.

Reglas:
1. Devuelve SOLO IDs de spans existentes en `spans[]`.
2. No inventes, reescribas ni combines texto.
3. Para `limit_source_to`, conserva únicamente spans que soporten el tema indicado en `topic`.
4. Para `exclude_topic`, conserva spans que NO pertenezcan al tema indicado en `topic`.
5. Si ningún span califica, devuelve `keep_ids` vacío.
6. Ante duda, sé conservador: conserva spans clínicamente útiles y no ambiguos.

Salida JSON:
{
  "keep_ids": ["1", "2"]
}
"""


def render_user_payload(
    *,
    directive: dict[str, object],
    spans: list[dict[str, object]],
) -> str:
    payload = {
        "directive": directive,
        "spans": spans,
    }
    blocks = render_block(
        "input_json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    return f"Selecciona los spans a conservar.\n\n{blocks}"


def output_schema(*, span_ids: list[str]) -> dict[str, object]:
    id_item: dict[str, object] = {"type": "string"}
    if span_ids:
        id_item["enum"] = span_ids
    return {
        "type": "object",
        "properties": {
            "keep_ids": {
                "type": "array",
                "items": id_item,
            }
        },
        "required": ["keep_ids"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_user_payload",
]
