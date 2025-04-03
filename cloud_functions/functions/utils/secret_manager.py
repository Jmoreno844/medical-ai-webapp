"""
Module for interacting with Google Cloud Secret Manager.
"""

import os
import logging
from google.cloud import secretmanager
from google.api_core.exceptions import NotFound, PermissionDenied

from config import is_production

# Initialize logger
logger = logging.getLogger(__name__)

# Global variables
_secret_client = None


def get_secret_client():
    """Get or create Secret Manager client"""
    global _secret_client

    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()

    return _secret_client


def access_secret(project_id, secret_name, version="latest"):
    """Access a secret from Secret Manager"""
    if not is_production():
        logger.info(
            f"Not in production, skipping Secret Manager access for {secret_name}"
        )
        return None

    try:
        client = get_secret_client()

        # Build the resource name
        if version == "latest":
            name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        else:
            name = f"projects/{project_id}/secrets/{secret_name}/versions/{version}"

        # Access the secret version
        response = client.access_secret_version(request={"name": name})

        # Return the decoded payload
        return response.payload.data.decode("UTF-8")

    except NotFound:
        logger.warning(f"Secret {secret_name} not found")
        return None
    except PermissionDenied:
        logger.error(f"Permission denied accessing secret {secret_name}")
        return None
    except Exception as e:
        logger.error(f"Error accessing secret {secret_name}: {str(e)}")
        return None


def load_environment_from_secret_manager(project_id=None):
    """Load environment variables from Secret Manager in production"""
    if not is_production():
        logger.info("Not in production, skipping Secret Manager configuration")
        return False

    try:
        project_id = project_id or os.environ.get("PROJECT_ID")
        if not project_id:
            logger.error("PROJECT_ID not set, cannot load secrets")
            return False

        logger.info("Loading configuration from Secret Manager")

        # Load key configuration values from Secret Manager
        # Format: secret name -> environment variable name
        secrets_to_load = {
            "gemini-api-key": "GEMINI_API_KEY",
            "gemini-model": "GEMINI_MODEL",
            "temperature": "TEMPERATURE",
            "top-p": "TOP_P",
            "max-output-tokens": "MAX_OUTPUT_TOKENS",
        }

        # Load each secret and set as environment variable
        for secret_name, env_var in secrets_to_load.items():
            secret_value = access_secret(project_id, secret_name)
            if secret_value:
                os.environ[env_var] = secret_value
                logger.info(f"Loaded {env_var} from Secret Manager")
            else:
                logger.warning(f"Failed to load {env_var} from Secret Manager")

        return True

    except Exception as e:
        logger.error(f"Error loading secrets: {str(e)}")
        return False
