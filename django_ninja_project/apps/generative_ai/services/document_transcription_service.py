import os
import tempfile
import logging
from typing import Dict, BinaryIO

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.conf import settings

# Import document model
from apps.documentos.models import Documento
from apps.encuentro.models import Encuentro
from .transcription_service import transcribe_audio

logger = logging.getLogger(__name__)


def get_document_for_transcription(documento_id: int, user_id: int) -> Documento:
    """
    Get a document for transcription and validate permissions.

    Args:
        documento_id: ID of the document
        user_id: ID of the requesting user

    Returns:
        The document object if found and accessible

    Raises:
        Http404: If document not found
        PermissionDenied: If user doesn't have permission
        ValueError: If document is not of type 'transcripcion'
    """
    try:
        documento = Documento.objects.get(id=documento_id)
    except Documento.DoesNotExist:
        raise Http404("Document not found")

    # Check document type
    if documento.tipo != "transcripcion":
        raise ValueError("Document is not of type 'transcripcion'")

    # Convert both IDs to strings for comparison to avoid type mismatches
    doc_medico_id = str(documento.id_medico) if documento.id_medico else ""
    user_id_str = str(user_id)

    # Log the comparison for debugging
    logger.debug(
        f"Comparing document id_medico: '{doc_medico_id}' with user_id: '{user_id_str}'"
    )

    # Check that the document belongs to the authenticated user
    if doc_medico_id != user_id_str:
        # If the document has a reference to a user model instead of just an ID
        # try checking for the ID attribute
        if (
            hasattr(documento.id_medico, "id")
            and str(documento.id_medico.id) == user_id_str
        ):
            # This is fine - the user is authorized
            pass
        else:
            logger.warning(
                f"Permission denied - doc_medico_id: {doc_medico_id}, user_id: {user_id_str}"
            )
            raise PermissionDenied(
                "You don't have permission to transcribe this document"
            )

    return documento


def process_document_audio(documento: Documento, format: str = "speakers") -> Dict:
    """
    Process the audio file associated with a document.

    Args:
        documento: The document object
        format: The transcription format

    Returns:
        Dict with transcription result

    Raises:
        ValueError: If no audio file is associated or processing fails
    """
    # Since Documento doesn't have an archivo field directly, we need to
    # find the audio from the associated encounter or from contenido

    # Option 1: Check if contenido contains a path to an audio file
    if documento.contenido and (
        documento.contenido.endswith(".mp3")
        or documento.contenido.endswith(".wav")
        or documento.contenido.endswith(".m4a")
    ):
        audio_path = documento.contenido
        if not os.path.isabs(audio_path):
            # If it's a relative path, make it absolute based on MEDIA_ROOT
            audio_path = os.path.join(settings.MEDIA_ROOT, audio_path)

        if not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found: {audio_path}")

        # Determine MIME type based on file extension
        mime_type = "audio/mpeg"  # Default
        if audio_path.endswith(".wav"):
            mime_type = "audio/wav"
        elif audio_path.endswith(".m4a"):
            mime_type = "audio/mp4"

        # Transcribe the audio file
        result = transcribe_audio(audio_path, mime_type, format)

    # Option 2: Check if there's an audio file associated with the encounter
    elif (
        hasattr(documento.id_encuentro, "audio_file")
        and documento.id_encuentro.audio_file
    ):
        # Use the audio file from the encounter
        audio_file = documento.id_encuentro.audio_file

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            for chunk in audio_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        try:
            mime_type = audio_file.content_type or "audio/mpeg"
            result = transcribe_audio(temp_file_path, mime_type, format)
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    # Option 3: The document ID refers to an encounter ID that has an associated audio file
    else:
        # Fetch all audio files in the encounter
        encuentro = documento.id_encuentro
        audio_files = Encuentro.objects.filter(id=encuentro.id).values_list(
            "audio_files", flat=True
        )

        if not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found: {audio_path}")

        # Determine MIME type
        mime_type = "audio/mpeg"  # Default
        if audio_path.endswith(".wav"):
            mime_type = "audio/wav"
        elif audio_path.endswith(".m4a"):
            mime_type = "audio/mp4"

        # Transcribe the audio
        result = transcribe_audio(audio_path, mime_type, format)

    # Update the document with the transcription result
    documento.contenido = result["transcript"]
    documento.save()

    logger.info(
        f"Updated document {documento.id} with transcription of length {len(result['transcript'])}"
    )

    return result


def process_document_with_uploaded_file(
    documento: Documento, uploaded_file, format: str = "speakers"
) -> Dict:
    """
    Process an uploaded audio file and update the document's content.

    Args:
        documento: The document object
        uploaded_file: The uploaded audio file from the request
        format: The transcription format

    Returns:
        Dict with transcription result

    Raises:
        ValueError: If processing fails
    """
    try:
        # Process the uploaded audio file using the existing service
        from .transcription_service import process_uploaded_audio

        result = process_uploaded_audio(uploaded_file, format)

        # Update the document with the transcription result
        documento.contenido = result["transcript"]
        documento.save()

        logger.info(
            f"Updated document {documento.id} with transcription of length {len(result['transcript'])}"
        )

        return result
    except Exception as e:
        logger.error(
            f"Error processing uploaded file for document {documento.id}: {str(e)}"
        )
        raise ValueError(f"Failed to process audio file: {str(e)}")


def transcribe_document(
    documento_id: int, user_id: int, format: str = "speakers"
) -> Dict:
    """
    Main function to handle document transcription workflow.

    Args:
        documento_id: ID of the document to transcribe
        user_id: ID of the requesting user
        format: The transcription format

    Returns:
        Dict with transcription result and metadata

    Raises:
        Http404: If document not found
        PermissionDenied: If user doesn't have permission
        ValueError: For various validation errors
    """
    # Get and validate document
    documento = get_document_for_transcription(documento_id, user_id)

    # Process the document's audio file
    result = process_document_audio(documento, format)

    # Return result with document ID added
    result.update({"documento_id": documento.id})

    return result


def transcribe_document_with_uploaded_file(
    documento_id: int, user_id: int, uploaded_file, format: str = "speakers"
) -> Dict:
    """
    Main function to handle document transcription workflow with an uploaded file.

    Args:
        documento_id: ID of the document to update
        user_id: ID of the requesting user
        uploaded_file: The uploaded audio file
        format: The transcription format

    Returns:
        Dict with transcription result and metadata

    Raises:
        Http404: If document not found
        PermissionDenied: If user doesn't have permission
        ValueError: For various validation errors
    """
    # Get and validate document
    documento = get_document_for_transcription(documento_id, user_id)

    # Process the uploaded audio file
    result = process_document_with_uploaded_file(documento, uploaded_file, format)

    # Return result with document ID added
    result.update({"documento_id": documento.id})

    return result
