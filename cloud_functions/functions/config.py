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
Please summarize the following medical text professionally, maintaining the
important clinical information and organizing it clearly:

{text}

Summary:
"""

TRANSLATE_PROMPT = """
Please translate the following medical text from Spanish to English, preserving all
relevant clinical terminology:

{text}

English translation:
"""

DOCUMENT_GENERATION_PROMPT = """
Your task is to generate a medical document based on the following components:

1. TEMPLATE: 
{template}

2. PATIENT CONTEXT:
{context}

3. CONVERSATION TRANSCRIPT:
{transcription}

Instructions:
- Use the structure provided in the TEMPLATE.
- Complete each section with relevant information from the CONTEXT and TRANSCRIPT.
- Maintain a professional and medical tone throughout.
- If there are sections in the template that cannot be completed with the available information,
  indicate it with "Information not available" or provide an appropriate generic observation.
- Ensure the final document is coherent and follows medical conventions.
- Include dates, times, and any specific data mentioned in the transcript.
- Do not invent information that is not present in the provided data.

Generate the complete document:
"""

TRANSCRIPTION_PROMPT = """
You are a professional medical transcriber. Please transcribe the following audio accurately, focusing on medical terminology and maintaining clarity.
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


def get_environment():
    """Determine the current environment"""
    env = os.environ.get("ENVIRONMENT", "").lower()

    # If environment explicitly set
    if env in ["dev", "test", "production"]:
        return env

    #

    # Default to local
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
    if not is_local():
        logger.info("Not in local environment, skipping .env file loading")
        return False

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
    logger.info(f"Detected environment: {env}")

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
