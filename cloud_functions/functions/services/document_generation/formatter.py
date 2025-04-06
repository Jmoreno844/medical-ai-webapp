"""
Formatting utilities for document generation.
"""

import logging
from config import (
    SUMMARY_PROMPT,
    TRANSLATE_PROMPT,
    DOCUMENT_GENERATION_PROMPT,
)

# Initialize logger
logger = logging.getLogger(__name__)

# Define expand prompt (not available in config.py)
EXPAND_PROMPT = """
Expande y proporciona más detalles sobre el siguiente texto:

{text}

Versión expandida:
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
