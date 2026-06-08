from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = """
Eres un extractor clínico conservador para una etapa shadow. Extrae solo hechos
explícitos de la consulta actual y devuelve JSON válido contra el schema.

Reglas obligatorias:
1. Cita primero: cada campo no nulo debe estar sustentado por evidence.quote
   verbatim, contigua y de un solo turno. No corrijas ASR, no uses elipsis.
2. supports_fields debe listar solo campos hermanos sustentados por esa cita.
3. Si algo no se dijo, devuelve null o [] según el schema. No inventes defaults.
4. No infieras unidad, frecuencia, vía, lateralidad, sexo, normalidad ni fechas.
5. Usa *_raw con palabras textuales; no normalices diagnósticos ni marcas.
6. Preguntas no son hechos salvo que una respuesta explícita las complete.
7. Separa sujeto, fuente de información y hablante.
8. Puedes sugerir chunk_hint, pero la cita debe ser verbatim.
9. No emitas metadatos administrativos; el backend los inyecta.
""".strip()


def build_extraction_prompt(work_item: dict[str, Any]) -> str:
    chunks = work_item.get("chunks") or []
    lines = [
        "Extrae ClinicalFactsV1 desde estos chunks diarizados.",
        f"session_id: {work_item.get('session_id')}",
        f"language: {work_item.get('language')}",
        "",
        "Chunks:",
    ]
    for chunk in chunks:
        lines.append(
            "[{chunk_id}] speaker={speaker} section={section}: {text}".format(
                chunk_id=chunk.get("chunk_id"),
                speaker=chunk.get("speaker"),
                section=chunk.get("section_index"),
                text=chunk.get("text"),
            )
        )
    return "\n".join(lines)
