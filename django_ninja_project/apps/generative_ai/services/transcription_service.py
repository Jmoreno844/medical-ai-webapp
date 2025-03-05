import os
import tempfile
from typing import Dict, Optional, BinaryIO

from vertexai.generative_models import Part, GenerationConfig

from .gemini_service import get_gemini_model, create_generation_config


def transcribe_audio(
    audio_file_path: str,
    mime_type: str,
    transcript_format: str = "timecode",
    model_name: str = "gemini-2.0-flash-001",
) -> Dict:
    """
    Transcribe an audio file using Google's Gemini model.

    Args:
        audio_file_path: Path to the audio file
        mime_type: MIME type of the audio file (e.g., "audio/mpeg")
        transcript_format: Format for transcript output (default: "timecode", other options: "plain", "speakers")
        model_name: The Gemini model to use (default: "gemini-2.0-flash-001")

    Returns:
        Dict containing the transcription and metadata

    Raises:
        ValueError: If the file cannot be processed or transcribed
    """
    try:
        # Get the model - need to use model that supports audio transcription
        model = get_gemini_model(model_name)

        # Create audio part from file path
        audio_part = Part.from_file(audio_file_path, mime_type=mime_type)

        # Format prompt based on requested transcript format
        use_timestamps = True
        if transcript_format == "timecode":
            prompt = """
            Por favor, transcribe esta conversación médica en español, utilizando el formato de código de tiempo, hablante y texto.
            Identifica a los participantes como "Médico:" y "Paciente:" de manera precisa.
            Asegúrate de capturar correctamente la terminología médica, diagnósticos, síntomas y tratamientos mencionados.
            Mantén la precisión clínica del lenguaje utilizado en la consulta.
            """
        elif transcript_format == "plain":
            prompt = """
            Por favor, transcribe esta consulta médica en español como texto continuo, sin marcas de tiempo ni etiquetas de hablantes.
            Crea una transcripción completa y fluida de todo el contenido médico, manteniendo la terminología médica exacta, 
            los diagnósticos, tratamientos y recomendaciones tal como se mencionan.
            Preserva el contexto clínico de la conversación.
            """
            use_timestamps = False
        elif transcript_format == "speakers":
            prompt = """
            Por favor, transcribe esta consulta médica en español identificando claramente cuando habla el médico y el paciente, 
            pero sin incluir marcas de tiempo. Utiliza "Médico:" y "Paciente:" al inicio de cada turno de conversación.
            Asegúrate de mantener con precisión todos los términos médicos especializados, nombres de medicamentos, 
            diagnósticos, procedimientos y síntomas descritos en la conversación.
            """
            use_timestamps = False
        else:
            # Default case - basic transcription with speaker identification
            prompt = """
            Por favor, transcribe esta conversación médica en español, diferenciando claramente entre el médico y el paciente.
            Mantén con precisión toda la terminología médica, diagnósticos, medicamentos y procedimientos mencionados.
            """
            use_timestamps = False

        # Prepare content for generation
        contents = [audio_part, prompt]

        # Create generation config with audio timestamp settings
        config_dict = create_generation_config(
            temperature=0.2,  # Lower temperature for more deterministic output
            max_output_tokens=8192,
        )._asdict()

        # Add audio timestamp parameter based on format setting
        generation_config = GenerationConfig(
            **config_dict, audio_timestamp=use_timestamps
        )

        # Generate transcription
        response = model.generate_content(contents, generation_config=generation_config)

        # Return the transcription with metadata
        return {
            "transcript": response.text,
            "format": transcript_format,
            "model": model_name,
        }

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Transcription error: {str(e)}")
        raise ValueError(f"Failed to transcribe audio: {str(e)}")


def process_uploaded_audio(uploaded_file, transcript_format: str = "timecode") -> Dict:
    """
    Process an uploaded audio file and return its transcription.

    Args:
        uploaded_file: The uploaded file from the request
        transcript_format: Format for the transcript output

    Returns:
        Dict containing the transcription and metadata

    Raises:
        ValueError: If processing fails
    """
    # Create a temporary file to store the uploaded content
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_file_path = temp_file.name

    try:
        # Get the MIME type from the uploaded file
        mime_type = uploaded_file.content_type

        # Transcribe the audio
        result = transcribe_audio(temp_file_path, mime_type, transcript_format)

        return result
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
