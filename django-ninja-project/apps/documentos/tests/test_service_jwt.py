"""Smoke tests for service JWT helpers (encode/decode round-trip)."""

import jwt
from django.test import TestCase, override_settings

from utils.jwt_settings import get_jwt_signing_key
from utils.service_jwt import (
    build_transcription_callback_payload,
    encode_service_jwt,
)


class ServiceJwtTests(TestCase):
    @override_settings(JWT_SECRET_KEY="test-secret-for-jwt", SECRET_KEY="fallback")
    def test_transcription_payload_roundtrip(self):
        payload = build_transcription_callback_payload(user_id=1, documento_id=42)
        token = encode_service_jwt(payload)
        decoded = jwt.decode(token, get_jwt_signing_key(), algorithms=["HS256"])
        self.assertEqual(decoded["id_usuario"], 1)
        self.assertEqual(decoded["id_documento"], 42)
        self.assertEqual(decoded["purpose"], "transcription")
