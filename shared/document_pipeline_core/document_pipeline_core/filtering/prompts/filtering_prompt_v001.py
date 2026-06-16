from __future__ import annotations

import json

from document_pipeline_core.common.prompt_blocks import render_block
from document_pipeline_core.filtering.protection import (
    TurnProtectionResult,
    build_filtering_v002_payload,
    compute_turn_protection,
)

SYSTEM_PROMPT = """# Identity

Eres un detector de basura en transcripciones clínicas para un scribe médico con IA.

# Task

Recibirás un JSON con:

- `drop_eligible_turn_ids`: turnos que el sistema ya marcó como candidatos a descarte.
- `turns[]`: turnos con `turn_id`, `speaker`, `text` y `can_drop`.

Tu tarea NO es resumir, comprimir ni eliminar redundancia clínica.

Tu tarea es identificar, dentro de `drop_eligible_turn_ids`, únicamente turnos que son claramente basura conversacional o ruido no clínico.

# Core principle

Eres un garbage detector, no un summarizer.

Ante la duda, conserva.

Solo puedes devolver IDs que estén en `drop_eligible_turn_ids`.

Nunca devuelvas un turno con `can_drop=false`.

# Forbidden deletions

Nunca descartes un turno elegible solo porque:

- sea una pregunta clínica del médico,
- sea una pregunta clínica del paciente,
- sea una respuesta breve con significado clínico por contexto vecino,
- repita información ya dicha,
- parezca redundante pero conserve señal clínica, contextual o comunicativa.

# Allowed deletions

Solo descarta turnos elegibles si son claramente:

- saludo o despedida aislada sin apertura clínica,
- cortesía social sin contenido médico ni contextual relevante,
- backchannel puro sin valor clínico posible,
- charla informal claramente no relacionada con salud o atención,
- artefacto de ASR, texto vacío, ininteligible o ruido sin términos clínicos recuperables,
- broma o comentario ambiental sin relevancia médica probable,
- ruido administrativo no clínico (audio, conexión, pago, estacionamiento, sala de espera, logística no clínica).

# Input contract

`can_drop=false` significa que el turno es contexto protegido y nunca puede aparecer en `drop_turn_ids`.

`drop_eligible_turn_ids` es el único conjunto válido para tu salida.

Evalúa contexto vecino cuando un turno corto o ambiguo pueda tener significado clínico.

# Output format

Devuelve únicamente JSON válido con esta forma:

{
  "drop_turn_ids": [3, 17, 42]
}

# Output rules

- Incluye solo turn_id presentes en `drop_eligible_turn_ids`.
- Si ningún turno elegible debe descartarse, devuelve {"drop_turn_ids": []}.
- No inventes ids.
- No incluyas claves adicionales.
- No incluyas razonamiento, explicaciones, comentarios ni markdown.
- No incluyas fences de código."""


def render_user_payload(
    *,
    turns: list[dict[str, object]],
    protection: TurnProtectionResult | None = None,
) -> str:
    if not turns:
        raise ValueError("filtering_v002_payload_requires_at_least_one_turn")
    resolved_protection = protection or compute_turn_protection(turns)
    payload, _payload_mode = build_filtering_v002_payload(turns, resolved_protection)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return render_block("transcript", body)


def output_schema(*, drop_eligible_turn_ids: list[int]) -> dict[str, object]:
    item_schema: dict[str, object] = {"type": "integer"}
    if drop_eligible_turn_ids:
        item_schema["enum"] = list(drop_eligible_turn_ids)
    return {
        "type": "object",
        "properties": {
            "drop_turn_ids": {
                "type": "array",
                "items": item_schema,
            },
        },
        "required": ["drop_turn_ids"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_user_payload",
]
