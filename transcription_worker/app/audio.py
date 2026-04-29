from __future__ import annotations

import subprocess

import numpy as np
from google.cloud import storage

from app.settings import Settings


def download_gcs_object(settings: Settings, object_name: str) -> bytes:
    if not settings.gcs_bucket_name:
        raise ValueError("GCS_BUCKET_NAME is required")
    client = storage.Client(project=settings.gcp_project_id)
    bucket = client.bucket(settings.gcs_bucket_name)
    return bucket.blob(object_name).download_as_bytes()


def decode_audio_to_float32_pcm(audio_bytes: bytes) -> np.ndarray:
    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "pipe:1",
        ],
        input=audio_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise ValueError("audio_decode_failed")
    return np.frombuffer(process.stdout, dtype=np.float32)
