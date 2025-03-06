from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def process_transcription_task(document_id, file_path, format="speakers"):
    """
    Process audio transcription in a background task.

    Args:
        document_id: ID of the document to update
        file_path: Path to the temporary audio file
        format: The transcription format
    """
    from apps.documentos.models import Documento
    from apps.generative_ai.services.transcription_service import transcribe_audio
    import os

    logger.info(f"Starting transcription task for document {document_id}")

    try:
        # Get the document
        documento = Documento.objects.get(id=document_id)

        # Determine mime type from file extension
        mime_type = "audio/mpeg"
        if file_path.endswith(".wav"):
            mime_type = "audio/wav"
        elif file_path.endswith(".m4a"):
            mime_type = "audio/mp4"

        # Transcribe the audio
        result = transcribe_audio(file_path, mime_type, format)

        # Update the document with the transcription
        documento.contenido = result["transcript"]
        documento.save()

        logger.info(f"Successfully transcribed document {document_id}")
        return {
            "success": True,
            "document_id": document_id,
            "transcript_length": len(result["transcript"]),
        }

    except Exception as e:
        logger.error(
            f"Error in transcription task for document {document_id}: {str(e)}"
        )
        return {"success": False, "error": str(e)}
    finally:
        # Clean up the temporary file if it exists
        if os.path.exists(file_path):
            os.unlink(file_path)
