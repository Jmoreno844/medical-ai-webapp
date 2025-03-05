import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel

# Module-level initialization flags - happens only once when the module is imported
_vertexai_initialized = False
_model_instance = None
_current_model_name = None  # Track the current model name separately


def initialize_vertexai(project_id="nodal-wall-426818-t6", location="us-central1"):
    """
    Initialize the Vertex AI Python SDK.

    Args:
        project_id: Google Cloud project ID
        location: Google Cloud region

    Note:
        Uses a module-level flag to ensure initialization happens only once.
    """
    global _vertexai_initialized
    if not _vertexai_initialized:
        vertexai.init(project=project_id, location=location)
        _vertexai_initialized = True


def get_gemini_model(model_name="gemini-2.0-flash"):
    """
    Get the specified Gemini model instance, initializing it if necessary.

    Args:
        model_name: The name of the Gemini model to use (default: "gemini-2.0-flash")

    Returns:
        GenerativeModel instance

    Note:
        Uses a module-level singleton pattern to ensure only one model instance exists.
    """
    global _model_instance, _current_model_name

    # Initialize Vertex AI if not already initialized
    initialize_vertexai()

    # Create new model instance if it doesn't exist or if model name is different
    if _model_instance is None or _current_model_name != model_name:
        _model_instance = GenerativeModel(model_name)
        _current_model_name = model_name  # Store the model name separately

    return _model_instance


def create_generation_config(
    temperature=1.0, top_p=0.95, max_output_tokens=8192, candidate_count=1
):
    """
    Create a standardized generation configuration for Vertex AI Gemini.

    Args:
        temperature: Controls randomness in responses (0-1)
        top_p: Controls diversity via nucleus sampling
        max_output_tokens: Maximum length of generated content
        candidate_count: Number of response candidates to generate

    Returns:
        GenerationConfig object
    """
    return GenerationConfig(
        temperature=temperature,
        top_p=top_p,
        max_output_tokens=max_output_tokens,
        candidate_count=candidate_count,
    )
