"""
Utilities for setting up and configuring logging.
"""

import logging
import os
from config import is_production


def setup_logging():
    """Configure logging based on environment"""
    log_level = os.environ.get("LOG_LEVEL", "INFO")

    # Set up basic configuration with improved format
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set lower log level for our own modules to see more details
    logging.getLogger("services").setLevel(logging.DEBUG)

    # For production, we might want to add additional handlers
    # like structured logging for Cloud Logging
    if is_production():
        # Could add Cloud Logging handler here
        pass

    logger = logging.getLogger()
    logger.info(f"Logging initialized at {log_level} level")

    return logger
