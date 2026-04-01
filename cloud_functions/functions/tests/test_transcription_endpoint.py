import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

fake_audio_processor = types.ModuleType("services.transcription.audio_processor")
fake_audio_processor.transcribe_audio = lambda _audio_uri: {
    "success": True,
    "transcript": "",
    "model": "fake-model",
}
sys.modules.setdefault("services.transcription.audio_processor", fake_audio_processor)

from endpoints.transcription_endpoint import _transcription_endpoint_impl


class FakeRequest:
    def __init__(self, payload, method="POST"):
        self.method = method
        self._payload = payload

    def get_json(self, silent=True):
        return self._payload


class TranscriptionEndpointTests(unittest.TestCase):
    @patch("endpoints.transcription_endpoint.update_document_content")
    @patch("endpoints.transcription_endpoint.transcribe_audio")
    def test_returns_422_and_skips_update_when_no_speech_detected(
        self, mock_transcribe_audio, mock_update_document
    ):
        mock_transcribe_audio.return_value = {
            "success": False,
            "error": "No intelligible speech detected in the audio",
            "error_code": "no_speech_detected",
            "model": "gemini-2.5-flash",
        }

        body, status, _headers = _transcription_endpoint_impl(
            FakeRequest(
                {
                    "document_id": 123,
                    "audio_uri": "gs://bucket/audio.wav",
                    "auth_token": "token",
                }
            )
        )

        payload = json.loads(body)
        self.assertEqual(status, 422)
        self.assertEqual(payload["error_code"], "no_speech_detected")
        mock_update_document.assert_not_called()

    @patch("endpoints.transcription_endpoint.update_document_content")
    @patch("endpoints.transcription_endpoint.transcribe_audio")
    def test_returns_500_when_transcription_fails(
        self, mock_transcribe_audio, mock_update_document
    ):
        mock_transcribe_audio.return_value = {
            "success": False,
            "error": "Transcription error: model timeout",
            "model": "gemini-2.5-flash",
        }

        body, status, _headers = _transcription_endpoint_impl(
            FakeRequest(
                {
                    "document_id": 123,
                    "audio_uri": "gs://bucket/audio.wav",
                    "auth_token": "token",
                }
            )
        )

        payload = json.loads(body)
        self.assertEqual(status, 500)
        self.assertIn("Transcription failed:", payload["error"])
        mock_update_document.assert_not_called()

    @patch("endpoints.transcription_endpoint.update_document_content")
    @patch("endpoints.transcription_endpoint.transcribe_audio")
    def test_updates_document_when_speech_is_detected(
        self, mock_transcribe_audio, mock_update_document
    ):
        mock_transcribe_audio.return_value = {
            "success": True,
            "transcript": "hola doctor",
            "model": "gemini-2.5-flash",
        }
        mock_update_document.return_value = {"success": True}

        body, status, _headers = _transcription_endpoint_impl(
            FakeRequest(
                {
                    "document_id": 123,
                    "audio_uri": "gs://bucket/audio.wav",
                    "auth_token": "token",
                }
            )
        )

        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        mock_update_document.assert_called_once_with(123, "hola doctor", "token")
