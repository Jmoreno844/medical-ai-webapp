from __future__ import annotations

import logging
import queue
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from google.api_core.client_options import ClientOptions
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

logger = logging.getLogger(__name__)

MAX_STREAMING_CHUNK_BYTES = 24_000


@dataclass(frozen=True)
class RealtimeSpeechConfig:
    project_id: str
    location: str = "us"
    language_codes: tuple[str, ...] = ("es-US",)
    model: str = "chirp_3"
    sample_rate_hertz: int = 16_000


class AudioRequestBridge:
    def __init__(self, config_request: cloud_speech.StreamingRecognizeRequest) -> None:
        self._config_request = config_request
        self._queue: queue.Queue[bytes | None] = queue.Queue()

    def put_audio(self, audio: bytes) -> None:
        if audio:
            self._queue.put(audio)

    def close(self) -> None:
        self._queue.put(None)

    def requests(self) -> Iterator[cloud_speech.StreamingRecognizeRequest]:
        yield self._config_request

        while True:
            chunk = self._queue.get()
            if chunk is None:
                return

            for start in range(0, len(chunk), MAX_STREAMING_CHUNK_BYTES):
                yield cloud_speech.StreamingRecognizeRequest(
                    audio=chunk[start : start + MAX_STREAMING_CHUNK_BYTES]
                )


def build_audio_bridge(config: RealtimeSpeechConfig) -> AudioRequestBridge:
    recognition_config = cloud_speech.RecognitionConfig(
        explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
            encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=config.sample_rate_hertz,
            audio_channel_count=1,
        ),
        language_codes=list(config.language_codes),
        model=config.model,
        features=cloud_speech.RecognitionFeatures(
            enable_automatic_punctuation=True,
        ),
    )
    streaming_config = cloud_speech.StreamingRecognitionConfig(
        config=recognition_config,
        streaming_features=cloud_speech.StreamingRecognitionFeatures(
            interim_results=True,
            enable_voice_activity_events=True,
        ),
    )
    config_request = cloud_speech.StreamingRecognizeRequest(
        recognizer=(
            f"projects/{config.project_id}/locations/{config.location}/recognizers/_"
        ),
        streaming_config=streaming_config,
    )
    return AudioRequestBridge(config_request)


def stream_realtime_transcription(
    bridge: AudioRequestBridge,
    config: RealtimeSpeechConfig,
    event_handler: Callable[[dict[str, object]], bool],
) -> None:
    client_options = None
    if config.location != "global":
        client_options = ClientOptions(
            api_endpoint=f"{config.location}-speech.googleapis.com"
        )

    client = SpeechClient(client_options=client_options)
    started_at = time.monotonic()

    for response in client.streaming_recognize(requests=bridge.requests()):
        for result in response.results:
            if not result.alternatives:
                continue

            alternative = result.alternatives[0]
            should_continue = event_handler(
                {
                    "type": "final" if result.is_final else "partial",
                    "transcript": alternative.transcript,
                    "is_final": result.is_final,
                    "stability": result.stability,
                    "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                }
            )
            if not should_continue:
                logger.info("Realtime STT stream stopped by websocket handler")
                return
