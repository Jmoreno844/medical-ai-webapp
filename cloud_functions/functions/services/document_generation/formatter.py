"""
Formatting utilities for document generation.
"""

import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Document generation prompts
SUMMARY_PROMPT = """
Proporciona un resumen breve y claro del siguiente texto, resaltando los puntos principales:

{text}

Resumen:
"""

EXPAND_PROMPT = """
Expande y proporciona más detalles sobre el siguiente texto:

{text}

Versión expandida:
"""

TRANSLATE_PROMPT = """
Traduce el siguiente texto del español al inglés, manteniendo el tono y estilo:

{text}

Traducción:
"""

DOCUMENT_GENERATION_PROMPT = """
Tu tarea es generar un documento médico basado en los siguientes componentes:

1. PLANTILLA: 
{template}

2. CONTEXTO DEL PACIENTE:
{context}

3. TRANSCRIPCIÓN DE LA CONVERSACIÓN:
{transcription}

Instrucciones:
- Utiliza la estructura proporcionada en la PLANTILLA.
- Completa cada sección con información relevante del CONTEXTO y la TRANSCRIPCIÓN.
- Mantén un tono profesional y médico en todo momento.
- Si hay secciones en la plantilla que no pueden ser completadas con la información disponible, 
  indícalo con "Información no disponible" o proporciona una observación genérica apropiada.
- Asegúrate de que el documento final sea coherente y siga las convenciones médicas.
- Incluye fechas, horas y cualquier dato específico mencionado en la transcripción.
- No inventes información que no esté presente en los datos proporcionados.

Genera el documento completo:
"""


def get_prompt_for_type(
    generation_type: str, content: str, custom_prompt: str = None
) -> str:
    """
    Get the appropriate prompt template for the given generation type.

    Args:
        generation_type: Type of generation (summarize, expand, translate)
        content: The content to process
        custom_prompt: Optional custom prompt to use instead of templates

    Returns:
        Formatted prompt string
    """
    if custom_prompt and isinstance(custom_prompt, str):
        # Use custom prompt and substitute {text} with content
        return custom_prompt.replace("{text}", content)
    elif custom_prompt and not isinstance(custom_prompt, str):
        # Log warning if custom_prompt is not a string
        logger.warning(
            f"Custom prompt is not a string: {type(custom_prompt)}. Using default prompt instead."
        )

    # Use predefined templates based on type
    if generation_type == "summarize":
        return SUMMARY_PROMPT.format(text=content)
    elif generation_type == "expand":
        return EXPAND_PROMPT.format(text=content)
    elif generation_type == "translate":
        return TRANSLATE_PROMPT.format(text=content)
    else:
        # Default to summary if unknown type
        logger.warning(f"Unknown generation type: {generation_type}, using summarize")
        return SUMMARY_PROMPT.format(text=content)
