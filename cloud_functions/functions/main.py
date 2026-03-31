"""
Main entry point for Cloud Functions.
"""

import tracing

tracing.configure_tracing()

import functions_framework
from endpoints.transcription_endpoint import transcription_endpoint
from endpoints.document_workflow import generate_document_workflow
#
# Export the Cloud Functions
transcription_endpoint = functions_framework.http(transcription_endpoint)
generate_document_workflow = functions_framework.http(generate_document_workflow)
