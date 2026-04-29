"""
Main entry point for Cloud Functions.
"""

import warnings

import functions_framework

import langsmith_tracing
import tracing
from endpoints.transcription_endpoint import transcription_endpoint

# google-cloud libraries may emit an alias migration FutureWarning at import time.
# This warning is non-actionable for local runtime and clutters container logs.
warnings.filterwarnings(
    "ignore",
    message=r".*google\\.cloud\\.resourcemanager_v3.*",
    category=FutureWarning,
)

tracing.configure_tracing()
langsmith_tracing.configure_langsmith()
#
# Export the Cloud Functions
transcription_endpoint = functions_framework.http(transcription_endpoint)
