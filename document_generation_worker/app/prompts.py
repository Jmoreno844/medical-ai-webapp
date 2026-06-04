DOCUMENT_GENERATION_PROMPT = """
Tu tarea es generar un documento médico basado en los siguientes componentes:

1. PLANTILLA:
{template}

2. CONTEXTO DEL MÉDICO:
{context}

3. TRANSCRIPCIÓN DE LA CONVERSACIÓN:
{transcription}

Instrucciones:
- Utiliza la estructura proporcionada en la PLANTILLA.
- Completa cada sección con información relevante del CONTEXTO y la TRANSCRIPCIÓN.
- Mantén un tono profesional y médico en todo momento.
- El documento final DEBE estar en Markdown clínico compatible con el editor.
- Usa encabezados Markdown (`#`, `##`, `###`) para secciones, listas con `-` para viñetas y `**negrita**` para etiquetas clínicas importantes cuando corresponda.
- No uses HTML, tablas HTML, XML ni bloques de código para envolver el documento.
- No conviertas listas de la plantilla a texto corrido si la estructura original usa viñetas.
- Omite cualquier sección de la plantilla si no se puede encontrar información en el contexto o la transcripción.
- No escribas marcadores de posición como "Información no disponible"; simplemente omite esas secciones.
- Asegúrate de que el documento final sea coherente y siga las convenciones médicas.
- Incluye fechas, horas y cualquier dato específico mencionado en la transcripción.
- No inventes información que no esté presente en los datos proporcionados.
- No conviertas una sospecha, posibilidad diagnóstica o diagnóstico por descartar en un hecho confirmado.
- Si el médico no afirma un diagnóstico de forma explícita, redacta con lenguaje prudente como "impresión clínica", "sugiere", "compatible con" o "a descartar", según corresponda a la fuente.
- No cierres diagnósticos, planes, incapacidades, fórmulas, remisiones, exámenes solicitados ni hallazgos negativos relevantes si no aparecen explícitamente en el CONTEXTO o la TRANSCRIPCIÓN.
- No infieras frases clínicas de mayor certeza que la fuente original. Por ejemplo, no conviertas "sin eritema ni dolor en piernas" en "sin signos de trombosis venosa profunda" salvo que el médico lo afirme.
- Distingue con claridad entre información referida por el paciente o acompañante, hallazgos del examen físico e interpretación clínica del médico.

Genera el documento basándote en la plantilla, excluyendo cualquier sección donde la información no esté disponible:
""".strip()


def build_document_prompt(
    *,
    template_content: str,
    context_content: str,
    transcription_content: str,
) -> str:
    return DOCUMENT_GENERATION_PROMPT.format(
        template=template_content,
        context=context_content,
        transcription=transcription_content,
    )
