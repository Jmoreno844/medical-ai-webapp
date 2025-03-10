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
Summarize the following text in a clear, comprehensive manner. Focus on extracting key medical information, diagnoses, symptoms, treatments, and follow-up recommendations. Structure the summary with appropriate headings and bullet points where relevant:

{text}
"""


def get_environment():
    """Determine the current environment"""
    env = os.environ.get("ENVIRONMENT", "").lower()

    # If environment explicitly set
    if env in ["local", "test", "production"]:
        return env

    # Auto-detect GitHub Actions
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "test"

    # Auto-detect Google Cloud Run
    if os.environ.get("K_SERVICE") or os.environ.get("FUNCTION_TARGET"):
        return "production"

    # Default to local
    return "local"


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
        from services.secret_manager import load_environment_from_secret_manager

        load_environment_from_secret_manager()
    elif is_test():
        # In test (GitHub Actions), environment variables are already set via GitHub Secrets
        logger.info("Using environment variables from GitHub Secrets")
    else:
        # In local development, use .env files
        load_environment_from_files()


# Initialize environment at module import time
initialize_environment()
