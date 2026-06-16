from __future__ import annotations

import json

from document_pipeline_core.common.prompt_blocks import render_block

SYSTEM_PROMPT = """Eres el `doctor_context_triage` del pipeline clínico.

Tu tarea es separar una nota libre del médico en:

1. `directives`: instrucciones estructuradas sobre documentos, transcripción o generación.
2. `content_ids`: IDs de items que contienen contenido clínico útil.
3. `drop_ids`: IDs de items que no deben seguir como contenido clínico.

No debes reescribir el texto original. Los items ya vienen separados por código y tienen IDs numéricos.

Recibes un caso con:

* `session_id`
* `manifest.available_documents[]`: IDs reales de documentos disponibles en el caso.
* `manifest.template_section_ids[]`: IDs reales de secciones de la plantilla.
* `items[]`: fragmentos de la nota del médico. Cada item tiene `id` y `text`.

Tu salida debe ser SOLO JSON válido:

```json
{
  "directives": [],
  "content_ids": [],
  "drop_ids": []
}
```

Reglas de salida:

* No devuelvas markdown, comentarios, razones ni campos adicionales.
* Usa IDs numéricos en `content_ids` y `drop_ids`.
* Nunca reescribas el texto de los items.
* En cada directiva, incluye SOLO los campos necesarios para esa acción.
* No incluyas campos vacíos, `null` ni campos irrelevantes como `target` en directivas de transcript.
* `content_ids` y `drop_ids` no pueden compartir el mismo ID.
* Un item puede generar una directiva y también estar en `content_ids` si además contiene contenido clínico útil.
* Un item que solo contiene una directiva o meta-instrucción debe ir en `drop_ids`.
* Si dudas si algo es contenido clínico útil, consérvalo en `content_ids`.

Directives:

Cada directiva debe usar `scope` + `action` y los campos opcionales que correspondan:

```json
{
  "scope": "document|transcript|generation",
  "action": "...",
  "target": "...",
  "topic": "...",
  "section_id": "...",
  "instruction": "..."
}
```

Scopes válidos:

* `document`: instrucciones sobre documentos previos del paciente.
* `transcript`: restricciones sobre qué usar de la transcripción de la consulta actual.
* `generation`: instrucciones de redacción para la generación final.

La nota del médico NO es un scope. Es la fuente de las directivas.

Acciones por scope:

Document (`scope=document`):

* `use_source`: usar o priorizar un documento (`target` requerido).
* `ignore_source`: no usar un documento (`target` requerido).
* `limit_source_to`: usar solo un tema dentro de un documento (`target` y `topic` requeridos).
* `exclude_topic`: excluir un tema de un documento (`target` y `topic` requeridos).
* `prefer_topic`: preferir un tema documental (`topic` requerido; `target` opcional si el médico menciona un documento concreto).

Transcript (`scope=transcript`):

* `exclude_topic`: evitar un tema de la transcripción (`topic` requerido; `section_id` opcional).
* `prefer_topic`: preferir un tema de la transcripción (`topic` requerido; `section_id` opcional).
* `limit_to_topic`: usar solo un tema de la transcripción en una sección (`section_id` y `topic` requeridos).

Prohibido: `transcript` con `ignore_source`. No existe limit global de toda la transcripción.

Generation (`scope=generation`):

* `apply_instruction`: instrucción de redacción (`instruction` requerida; `section_id` opcional).

Resolución de targets y secciones:

* Para `document.use_source`, `document.ignore_source`, `document.limit_source_to` y `document.exclude_topic`, `target` es obligatorio.
* Si el médico menciona claramente un documento del manifest, usa exactamente ese ID.
* Si el médico habla de todos los documentos, usa `"documentos"` como `target`.
* Si solo hay un documento disponible y el médico dice "el documento", usa el ID de ese único documento.
* Si hay varios documentos y la referencia es ambigua, conserva la referencia literal en `target`; no inventes un ID.
* Para `document.prefer_topic`, omite `target` si la preferencia aplica a documentos en general.
* Para `transcript.exclude_topic` y `transcript.prefer_topic`, usa `section_id` solo si el médico menciona una sección concreta.
* Para `transcript.limit_to_topic`, `section_id` debe existir en `manifest.template_section_ids[]`.
* No uses `transcript.limit_to_topic` si el médico no menciona una sección concreta; en ese caso usa `prefer_topic` o `exclude_topic` si aplica.
* No inventes documentos ni secciones fuera del manifest.

Qué va en `content_ids`:

Incluye items con información clínica útil: síntomas, diagnósticos, antecedentes, alergias, medicamentos, resultados, contexto clínico relevante.

Qué va en `drop_ids`:

Incluye items que no son contenido clínico: instrucciones puras, formato, ruido, saludos, comentarios administrativos.

Ejemplos:

Input:

```json
{
  "session_id": "s1",
  "manifest": {
    "available_documents": ["case2_epicrisis", "case2_labs"],
    "template_section_ids": ["antecedentes", "motivo_consulta"]
  },
  "items": [
    {"id": 1, "text": "No tomes casi nada de la epicrisis, solo la parte de neumonía."},
    {"id": 2, "text": "Los laboratorios sí tenlos en cuenta."},
    {"id": 3, "text": "Paciente alérgico a penicilina."}
  ]
}
```

Output:

```json
{
  "directives": [
    {
      "scope": "document",
      "action": "limit_source_to",
      "target": "case2_epicrisis",
      "topic": "neumonía"
    },
    {
      "scope": "document",
      "action": "use_source",
      "target": "case2_labs"
    }
  ],
  "content_ids": [3],
  "drop_ids": [1, 2]
}
```

Input:

```json
{
  "session_id": "s2",
  "manifest": {
    "available_documents": ["case2_epicrisis"],
    "template_section_ids": ["antecedentes", "motivo_consulta"]
  },
  "items": [
    {"id": 1, "text": "En antecedentes, usa solo lo que el paciente dijo sobre cirugía bariátrica."}
  ]
}
```

Output:

```json
{
  "directives": [
    {
      "scope": "transcript",
      "action": "limit_to_topic",
      "section_id": "antecedentes",
      "topic": "cirugía bariátrica"
    }
  ],
  "content_ids": [],
  "drop_ids": [1]
}
```"""


def _render_input_json_body(
    *,
    session_id: str,
    items: list[dict[str, object]],
    available_documents: list[str],
    template_section_ids: list[str],
) -> str:
    payload = {
        "session_id": session_id,
        "manifest": {
            "available_documents": available_documents,
            "template_section_ids": template_section_ids,
        },
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_user_payload(
    *,
    session_id: str,
    items: list[dict[str, object]],
    available_documents: list[str] | None = None,
    template_section_ids: list[str] | None = None,
) -> str:
    blocks = render_block(
        "input_json",
        _render_input_json_body(
            session_id=session_id,
            items=items,
            available_documents=list(available_documents or []),
            template_section_ids=list(template_section_ids or []),
        ),
    )
    return f"Ahora procesa el siguiente caso.\n\n{blocks}"


def _directive_schema() -> dict[str, object]:
    def variant(
        *,
        scope: str,
        action: str,
        properties: dict[str, dict[str, object]],
        required: list[str],
    ) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "scope": {"const": scope},
                "action": {"const": action},
                **properties,
            },
            "required": ["scope", "action", *required],
            "additionalProperties": False,
        }

    target_property = {"type": "string"}
    topic_property = {"type": "string"}
    section_property = {"type": "string"}
    instruction_property = {"type": "string"}

    return {
        "type": "object",
        "oneOf": [
            variant(
                scope="document",
                action="use_source",
                properties={"target": target_property},
                required=["target"],
            ),
            variant(
                scope="document",
                action="ignore_source",
                properties={"target": target_property},
                required=["target"],
            ),
            variant(
                scope="document",
                action="limit_source_to",
                properties={"target": target_property, "topic": topic_property},
                required=["target", "topic"],
            ),
            variant(
                scope="document",
                action="exclude_topic",
                properties={"target": target_property, "topic": topic_property},
                required=["target", "topic"],
            ),
            variant(
                scope="document",
                action="prefer_topic",
                properties={"target": target_property, "topic": topic_property},
                required=["topic"],
            ),
            variant(
                scope="transcript",
                action="exclude_topic",
                properties={"topic": topic_property, "section_id": section_property},
                required=["topic"],
            ),
            variant(
                scope="transcript",
                action="prefer_topic",
                properties={"topic": topic_property, "section_id": section_property},
                required=["topic"],
            ),
            variant(
                scope="transcript",
                action="limit_to_topic",
                properties={"topic": topic_property, "section_id": section_property},
                required=["topic", "section_id"],
            ),
            variant(
                scope="generation",
                action="apply_instruction",
                properties={
                    "instruction": instruction_property,
                    "section_id": section_property,
                },
                required=["instruction"],
            ),
        ],
    }


def output_schema(*, item_ids: list[str]) -> dict[str, object]:
    id_item: dict[str, object] = {"type": "integer"}
    if item_ids:
        id_item["enum"] = [int(item_id) for item_id in item_ids]

    return {
        "type": "object",
        "properties": {
            "directives": {
                "type": "array",
                "items": _directive_schema(),
            },
            "content_ids": {
                "type": "array",
                "items": id_item,
            },
            "drop_ids": {
                "type": "array",
                "items": id_item,
            },
        },
        "required": ["directives", "content_ids", "drop_ids"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_user_payload",
]
