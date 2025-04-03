"""
Main entry point for Cloud Functions.
"""

import functions_framework
from endpoints.transcription_endpoint import transcription_endpoint
from endpoints.document_streaming import document_streaming_generation
from endpoints.document_workflow import generate_document_workflow

# Export the Cloud Functions
transcription_endpoint = functions_framework.http(transcription_endpoint)
document_streaming_generation = functions_framework.http(document_streaming_generation)
generate_document_workflow = functions_framework.http(generate_document_workflow)
