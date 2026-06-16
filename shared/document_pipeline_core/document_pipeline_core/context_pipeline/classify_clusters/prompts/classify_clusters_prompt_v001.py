from __future__ import annotations

import json

from document_pipeline_core.common.prompt_blocks import join_blocks, render_block

SYSTEM_PROMPT = """# Identity

Eres un clasificador de clusters clínicos hacia secciones de una plantilla médica.

# Task

Debes asignar cada cluster clínico a cero, una o varias secciones candidatas de la plantilla.

No estás redactando la nota clínica final.
No estás decidiendo inclusión final del contenido.
Solo estás ruteando evidencia clínica hacia secciones posibles para procesamiento posterior.

# Core principle

Alta sensibilidad, pero no clasificación indiscriminada.

Asigna un cluster a todas las secciones plausibles cuando el contenido encaje razonablemente con las guías o descripciones de esas secciones.

Si el destino no es claro, usa `section_ids: []`.

# Authority and constraints

* Usa solo `section_id` definidos en `<template_sections>`.
* No inventes section_ids.
* No modifiques clusters.
* No modifiques spans.
* No reescribas texto.
* Cada cluster debe aparecer exactamente una vez.
* Un cluster puede asignarse a varias secciones si el contenido es transversal.
* No incluyas razones ni explicación fuera del JSON.

# Evidence rule

Para cada cluster:

1. Usa como evidencia principal los spans listados en `span_ids`.
2. Busca esos spans dentro de `<source_spans>`.
3. Usa `cluster_title` solo como señal auxiliar.
4. Usa `date_hints` solo como señal temporal auxiliar.
5. No uses spans de otros clusters como evidencia para clasificar el cluster actual.
6. Si algún `span_id` no aparece en `<source_spans>`, clasifica con la evidencia disponible.

# Template matching priority

Para decidir `section_ids`, usa esta prioridad:

1. Section-specific `classification_guidelines`, si existen.
2. Section `description`.
3. Section `heading`.
4. Heurísticas clínicas generales solo si la plantilla no resuelve la duda.

# General fallback heuristics

Usa estas heurísticas solo como fallback:

* Motivo actual de consulta o razón principal de la visita → motivo de consulta, chief complaint o equivalente.
* Evolución del problema actual → enfermedad actual, HPI o equivalente.
* Antecedentes personales, quirúrgicos, familiares, sociales, gineco-obstétricos, psiquiátricos o pediátricos → antecedentes o equivalente.
* Alergias → alergias o antecedentes si no existe sección específica.
* Medicamentos crónicos o medicación habitual → medicación o antecedentes si no existe sección específica.
* Síntomas por sistemas no claramente parte del problema principal → revisión por sistemas o equivalente.
* Hallazgos objetivos de exploración → examen físico o equivalente.
* Signos vitales y mediciones → signos vitales o examen físico si no existe sección específica.
* Laboratorios, imágenes, patología, electrocardiograma u otros estudios → resultados, pruebas diagnósticas o equivalente.
* Diagnósticos, interpretación médica, assessment, impresión o razonamiento clínico → assessment, impresión diagnóstica o equivalente.
* Tratamiento, órdenes, educación, derivaciones, seguimiento o conducta → plan o equivalente.

# Temporality rules

`encounter_date` es la fecha de la consulta actual.

`doc_date` es la fecha del documento fuente, si está disponible.

`date_hints` contiene fechas explícitas detectadas en los spans del cluster.

La fecha del documento no siempre es la fecha del evento clínico.
Si un span menciona otra fecha, esa fecha puede referirse al evento clínico dentro del documento.

No descartes ni evites clasificar un cluster solo porque sea antiguo.

# Historical-document routing

Si un cluster proviene de un documento previo o claramente describe eventos históricos:

* No lo clasifiques como motivo actual de consulta salvo que el texto lo conecte claramente con la consulta actual.
* No lo clasifiques como hallazgo físico actual salvo que el texto indique que fue observado en la consulta actual.
* No lo clasifiques como signo vital actual salvo que el texto indique que corresponde a la consulta actual.
* No lo clasifiques como plan actual salvo que el texto indique una conducta activa o relevante para la atención actual.

Sin embargo:

* Diagnósticos previos, cirugías, hospitalizaciones, alergias, medicamentos crónicos y antecedentes familiares/sociales pueden ir a antecedentes aunque sean antiguos.
* Laboratorios, imágenes, ECG, patología y pruebas previas pueden ir a resultados o pruebas diagnósticas si esa sección existe.
* Medicación previa o crónica puede ir a medicación si esa sección existe.
* Planes, tratamientos o instrucciones previas pueden ir a plan o sección relacionada solo si parecen activos, relevantes o necesarios para entender la atención actual.
* Eventos históricos importantes pueden mapear a assessment, antecedentes o resultados según la plantilla, pero no deben transformarse en eventos actuales.

# Safety-sensitive routing

Si un cluster menciona alergias, reacciones adversas, medicamentos críticos, diagnósticos mayores, cirugías importantes, hospitalizaciones, embarazo, anticoagulación, inmunosupresión, cáncer, infarto, ACV, trombosis, insuficiencia renal, insuficiencia cardiaca, diabetes, epilepsia o alertas de seguridad, asígnalo a todas las secciones plausibles donde pueda ser útil.

# Multi-section rule

Un cluster debe tener múltiples `section_ids` cuando su contenido sea naturalmente transversal.

Ejemplos:

* Alergia medicamentosa con reacción → alergias y antecedentes, si ambas existen.
* Diagnóstico previo con cirugía relacionada → antecedentes y procedimientos/cirugías, si ambas existen.
* Resultado de laboratorio que fundamenta una impresión diagnóstica → resultados y assessment, si ambas existen.
* Medicamento crónico relacionado con un diagnóstico mayor → medicación y antecedentes, si ambas existen.
* Plan previo todavía activo → plan y antecedentes/tratamientos, si ambas existen.

No agregues secciones solo porque podrían recibir cualquier contenido clínico genérico. Debe haber una relación razonable con la descripción o guidelines de la sección.

# Empty assignment rule

Usa `section_ids: []` cuando:

* El cluster no tiene contenido clínico suficiente.
* El cluster contiene solo ruido documental, boilerplate o metadatos.
* Ninguna sección de la plantilla encaja razonablemente.
* El contenido es demasiado ambiguo para rutearlo sin inventar contexto.

No omitas clusters.

# Internal procedure

Antes de responder, aplica este procedimiento internamente:

1. Lee `<template_sections>` y extrae los `section_id` válidos.
2. Lee `<encounter_context>` para interpretar temporalidad.
3. Para cada cluster en `<clusters>`, reúne sus spans desde `<source_spans>`.
4. Clasifica cada cluster usando solo su propia evidencia.
5. Asigna todas las secciones plausibles según la plantilla.
6. Usa `section_ids: []` si no hay destino claro.
7. Verifica que cada cluster aparezca exactamente una vez.
8. Verifica que cada `section_id` usado exista en `<template_sections>`.

No incluyas este razonamiento en la salida.

# Output format

Devuelve únicamente JSON válido con esta forma:

{
"assignments": [
{
"cluster_id": "cluster_1",
"section_ids": ["antecedentes", "medicacion"]
}
]
}

# Strict output rules

* Devuelve exactamente un objeto dentro de `assignments` por cada cluster de entrada.
* `cluster_id` debe coincidir exactamente con un cluster de `<clusters>`.
* `section_ids` debe ser un array.
* `section_ids` puede estar vacío.
* Cada `section_id` debe existir exactamente en `<template_sections>`.
* No repitas section_ids dentro del mismo cluster.
* No agregues claves extra.
* No incluyas razonamiento.
* No incluyas explicación fuera del JSON.
* No incluyas markdown.
* No incluyas fences de código."""


def _classification_guidelines_text(section_payload: dict[str, object]) -> str:
    guidelines = section_payload.get("classification_guidelines")
    if isinstance(guidelines, str) and guidelines.strip():
        return guidelines.strip()
    legacy_guidelines = section_payload.get("guidelines")
    if isinstance(legacy_guidelines, str) and legacy_guidelines.strip():
        return legacy_guidelines.strip()
    return ""


def _render_encounter_context_body(
    *,
    encounter_date: str | None,
    document_date: str | None,
) -> str:
    encounter_value = encounter_date if encounter_date else "null"
    document_value = document_date if document_date else "null"
    return "\n".join(
        [
            f"encounter_date: {encounter_value}",
            f"doc_date: {document_value}",
        ]
    )


def _render_template_sections_body(
    template_sections: list[dict[str, object]],
) -> str:
    section_blocks: list[str] = []
    for section in template_sections:
        section_id = str(section["section_id"])
        lines = [
            f'<section id="{section_id}">',
            f"heading: {section['heading']}",
            f"description: {section['description']}",
        ]
        guidelines = _classification_guidelines_text(section)
        if guidelines:
            lines.append("classification_guidelines:")
            lines.append(guidelines)
        lines.append("</section>")
        section_blocks.append("\n".join(lines))
    return "\n\n".join(section_blocks)


def _render_clusters_body(clusters: list[dict[str, object]]) -> str:
    cluster_blocks: list[str] = []
    for cluster in clusters:
        cluster_id = str(cluster["id"])
        lines = [f'<cluster id="{cluster_id}">']
        title = cluster.get("title")
        if isinstance(title, str) and title.strip():
            lines.append(f"title: {title.strip()}")
        span_ids = cluster.get("span_ids", [])
        if not isinstance(span_ids, list):
            span_ids = []
        lines.append(
            f"span_ids: {json.dumps(span_ids, ensure_ascii=False)}"
        )
        date_hints = cluster.get("date_hints", [])
        if not isinstance(date_hints, list):
            date_hints = []
        lines.append(
            f"date_hints: {json.dumps(date_hints, ensure_ascii=False)}"
        )
        lines.append("</cluster>")
        cluster_blocks.append("\n".join(lines))
    return "\n\n".join(cluster_blocks)


def _render_source_spans_body(spans: list[dict[str, object]]) -> str:
    span_blocks: list[str] = []
    for span in spans:
        span_id = str(span["id"])
        doc = str(span["doc"])
        kind = str(span["kind"])
        text = str(span["text"])
        span_blocks.append(
            f'<span id="{span_id}" doc="{doc}" kind="{kind}">\n{text}\n</span>'
        )
    return "\n\n".join(span_blocks)


def render_user_payload(
    *,
    template_sections: list[dict[str, object]],
    encounter_date: str | None,
    document_date: str | None,
    clusters: list[dict[str, object]],
    spans: list[dict[str, object]],
) -> str:
    return join_blocks(
        [
            render_block(
                "encounter_context",
                _render_encounter_context_body(
                    encounter_date=encounter_date,
                    document_date=document_date,
                ),
            ),
            render_block(
                "template_sections",
                _render_template_sections_body(template_sections),
            ),
            render_block("clusters", _render_clusters_body(clusters)),
            render_block("source_spans", _render_source_spans_body(spans)),
        ]
    )


def output_schema(
    *,
    cluster_ids: list[str],
    section_ids: list[str],
) -> dict[str, object]:
    cluster_id_item: dict[str, object] = {"type": "string"}
    if cluster_ids:
        cluster_id_item["enum"] = cluster_ids
    section_id_item: dict[str, object] = {"type": "string"}
    if section_ids:
        section_id_item["enum"] = section_ids
    assignment_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "cluster_id": cluster_id_item,
            "section_ids": {
                "type": "array",
                "items": section_id_item,
            },
        },
        "required": ["cluster_id", "section_ids"],
        "additionalProperties": False,
    }
    assignments_schema: dict[str, object] = {
        "type": "array",
        "items": assignment_schema,
    }
    if cluster_ids:
        assignments_schema["minItems"] = len(cluster_ids)
        assignments_schema["maxItems"] = len(cluster_ids)
    return {
        "type": "object",
        "properties": {
            "assignments": assignments_schema,
        },
        "required": ["assignments"],
        "additionalProperties": False,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "output_schema",
    "render_user_payload",
]
