"""
Configuration module for handling environment settings and initialization.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a single, optimized generation configuration
GENERATION_CONFIG = {
    "temperature": 0.4,  # Lower temperature for more factual responses
    "top_p": 0.95,  # Standard value for coherent output
    "max_output_tokens": 2048,  # Reasonable limit for comprehensive responses
    "candidate_count": 1,  # Single candidate for deterministic output
}

# Define a single, fixed prompt that instructs the model to summarize text
SUMMARY_PROMPT = """
Por favor, resume el siguiente texto médico de manera profesional, manteniendo
la información clínica importante y organizándola claramente:

{text}

Resumen:
"""

TRANSLATE_PROMPT = """
Por favor, traduce el siguiente texto médico del español al inglés, conservando toda
la terminología clínica relevante:

{text}

Traducción al inglés:
"""

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
- Omite cualquier sección de la plantilla si no se puede encontrar información en el contexto o la transcripción.
- No escribas marcadores de posición como "Información no disponible"; simplemente omite esas secciones.
- Asegúrate de que el documento final sea coherente y siga las convenciones médicas.
- Incluye fechas, horas y cualquier dato específico mencionado en la transcripción.
- No inventes información que no esté presente en los datos proporcionados.

Genera el documento basándote en la plantilla, excluyendo cualquier sección donde la información no esté disponible:
"""

TRANSCRIPTION_PROMPT = """
Eres un transcriptor médico profesional.

Transcribe únicamente el habla realmente presente en el audio.

Reglas obligatorias:
- No inventes palabras, frases, diagnósticos ni contexto.
- No completes silencios, ruido de fondo, respiración, golpes o audio ambiguo.
- Si el audio no contiene voz humana inteligible, responde exactamente con: NO_SPEECH_DETECTED
- Si solo una parte es inteligible, transcribe únicamente esa parte.
- No añadas explicaciones, notas ni encabezados.
"""

# Define Django API connection defaults (will be overridden by environment variables)
DJANGO_API_DEFAULTS = {
    "base_url": "http://localhost:8000/api",  # Default for local development
    "timeout": 30,  # Default timeout in seconds
}

# Gemini API Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-pro")
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.2"))
TOP_P = float(os.environ.get("TOP_P", "0.95"))
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "1024"))

_DOCKER_COMPOSE_ADC = "/app/adc.json"


def _is_docker_compose_local_dev() -> bool:
    """True when running our docker-compose stack (ADC mount + compose env path)."""
    ga = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if ga != _DOCKER_COMPOSE_ADC:
        return False
    return Path(_DOCKER_COMPOSE_ADC).exists()


def get_environment():
    """Determine the current environment"""
    # Strip: env_file / Windows CRLF can leave trailing \r on values
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()

    # env_file (.env.local) can override compose's ENVIRONMENT=local; treat compose+ADC as local
    if _is_docker_compose_local_dev() and env in ("", "dev"):
        return "local"

    if env in ("dev", "test", "production", "local"):
        return env

    return "dev"


def is_production():
    """Check if running in production environment"""
    return get_environment() == "production"


def is_test():
    """Check if running in test environment"""
    return get_environment() == "test"


def is_local():
    """Check if running in local environment"""
    return get_environment() == "local"


def load_environment_from_files():
    """Load environment variables from .env files in priority order"""
    # Try loading from different .env files in order of priority
    env_files = [".env.local", ".env"]

    for env_file in env_files:
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded environment from {env_file}")
            return True

    logger.warning("No .env file found, using system environment variables only")
    return False


def initialize_environment():
    """Load configuration from appropriate source based on environment"""
    env = get_environment()
    logger.debug(f"Detected environment: {env}")

    if is_production():
        # In production, use Secret Manager (Cloud Run function context)
        from cloud_functions.functions.utils.secret_manager import (
            load_environment_from_secret_manager,
        )

        load_environment_from_secret_manager()
    elif is_test():
        # In test (GitHub Actions), environment variables are already set via GitHub Secrets
        logger.info("Using environment variables from GitHub Secrets")
    else:
        # In local development, use .env files
        load_environment_from_files()


# Initialize environment at module import time
initialize_environment()
