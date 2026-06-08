from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import anyio

from app.audio import decode_audio_to_float32_pcm, download_gcs_object
from app.backend_client import BackendClient
from app.chunk_transcription import transcribe_chunk_audio
from app.debug_cuts import build_worker_debug_cut
from app.observability import bind_log_context, log_event
from app.settings import Settings
from app.vad import VadResult
from transcription_contract.models import TranscriptionTurn
from transcription_contract.sanitize import TranscriptParseError

logger = logging.getLogger(__name__)


@dataclass
class Processor:
    settings: Settings
    backend: BackendClient
    vad_semaphore: asyncio.Semaphore
    gemini_semaphore: asyncio.Semaphore

    @classmethod
    def create(cls, settings: Settings) -> "Processor":
        return cls(
            settings=settings,
            backend=BackendClient(settings),
            vad_semaphore=asyncio.Semaphore(settings.vad_max_concurrent),
            gemini_semaphore=asyncio.Semaphore(settings.gemini_max_concurrent),
        )

    async def process_section(self, section_id: str) -> None:
        started_at = time.monotonic()
        work_item = await self.backend.get_section_work_item(section_id)
        with bind_log_context(
            section_id=section_id,
            provider=self.settings.transcription_provider_name,
            model=self.settings.effective_transcription_model,
        ):
            try:
                turns, transcription_source, vad_result, error_code = (
                    await self._transcribe_with_frontend_clip_fallback(
                        work_item=work_item,
                    )
                )
            except TranscriptParseError as exc:
                await self.backend.post_section_result(
                    section_id,
                    {
                        "status": "failed_retryable",
                        "turns": None,
                        "error_code": "invalid_transcript_json",
                        "worker_latency_ms": self._elapsed_ms(started_at),
                    },
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "Transcript parse failed",
                    event="transcript_parse_failed",
                    error_code=exc.__class__.__name__,
                    duration_ms=self._elapsed_ms(started_at),
                )
                return

            if (
                transcription_source == "fallback_worker_from_original"
                and not vad_result.is_speech
                and vad_result.error_code is None
            ):
                await self.backend.post_section_result(
                    section_id,
                    {
                        "status": "discarded_no_speech",
                        "turns": [],
                        "error_code": "no_speech_detected",
                        "vad_decision": "no_speech",
                        "vad_speech_ms": vad_result.speech_ms,
                        "vad_speech_ratio": vad_result.speech_ratio,
                        "worker_latency_ms": self._elapsed_ms(started_at),
                        "transcription_source": transcription_source,
                    },
                )
                return
            await self.backend.post_section_result(
                section_id,
                {
                    "status": "transcribed",
                    "turns": _serialize_turns(turns),
                    "error_code": error_code,
                    "vad_decision": "speech"
                    if vad_result.error_code is None
                    else "fail_open",
                    "vad_speech_ms": vad_result.speech_ms,
                    "vad_speech_ratio": vad_result.speech_ratio,
                    "vad_error_code": vad_result.error_code,
                    "transcription_provider": self.settings.transcription_provider_name,
                    "transcription_model": self.settings.effective_transcription_model,
                    "worker_latency_ms": self._elapsed_ms(started_at),
                    "transcription_source": transcription_source,
                },
            )
            log_event(
                logger,
                logging.INFO,
                "Section processed",
                event="section_processed",
                error_code=error_code,
                duration_ms=self._elapsed_ms(started_at),
            )

    async def _download_audio_bytes(self, gcs_object_name: str) -> bytes:
        return await anyio.to_thread.run_sync(
            download_gcs_object,
            self.settings,
            gcs_object_name,
        )

    async def _transcribe_with_frontend_clip_fallback(
        self,
        *,
        work_item: dict[str, str],
    ) -> tuple[list[TranscriptionTurn], str, VadResult, str | None]:
        # Primary path: transcribe the frontend-clipped GCS artifact as-is.
        # Worker Silero VAD runs only on the original-audio fallback below.
        clipped_gcs_uri = work_item.get("clipped_gcs_uri") or work_item[
            "transcription_source_gcs_uri"
        ]
        clipped_content_type = work_item.get("clipped_content_type") or work_item[
            "transcription_source_content_type"
        ]
        async with self.gemini_semaphore:
            clipped_turns = await transcribe_chunk_audio(
                gcs_uri=clipped_gcs_uri,
                content_type=clipped_content_type,
                audio_bytes=None,
                settings=self.settings,
            )
        if clipped_turns:
            return (
                clipped_turns,
                "clipped_frontend",
                VadResult(
                    is_speech=True,
                    speech_ms=0,
                    speech_ratio=0.0,
                    error_code=None,
                ),
                None,
            )

        original_object_name = work_item.get("original_gcs_object_name")
        if not original_object_name:
            return (
                clipped_turns,
                "clipped_frontend",
                VadResult(
                    is_speech=True,
                    speech_ms=0,
                    speech_ratio=0.0,
                    error_code=None,
                ),
                "empty_or_noise_only_transcript",
            )

        original_audio_bytes = await self._download_audio_bytes(original_object_name)
        vad_result, fallback_audio_bytes = await self._build_worker_fallback_audio(
            original_audio_bytes,
        )
        if not vad_result.is_speech and vad_result.error_code is None:
            return (
                [],
                "fallback_worker_from_original",
                vad_result,
                "no_speech_detected",
            )

        async with self.gemini_semaphore:
            fallback_turns = await transcribe_chunk_audio(
                gcs_uri=None,
                content_type="audio/wav",
                audio_bytes=fallback_audio_bytes,
                settings=self.settings,
            )
        return (
            fallback_turns,
            "fallback_worker_from_original",
            vad_result,
            None,
        )

    async def _build_worker_fallback_audio(
        self,
        audio_bytes: bytes,
    ) -> tuple[VadResult, bytes]:
        try:
            async with self.vad_semaphore:
                samples = await anyio.to_thread.run_sync(
                    decode_audio_to_float32_pcm,
                    audio_bytes,
                )
                analysis, _worker_cut, trimmed_audio_bytes = (
                    await anyio.to_thread.run_sync(
                        build_worker_debug_cut,
                        samples,
                        self.settings,
                    )
                )
                return (
                    VadResult(
                        is_speech=analysis.is_speech,
                        speech_ms=analysis.speech_ms,
                        speech_ratio=analysis.speech_ratio,
                        error_code=analysis.error_code,
                    ),
                    trimmed_audio_bytes,
                )
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "VAD fail open",
                event="vad_fail_open",
                error_code=exc.__class__.__name__,
            )
            return (
                VadResult(
                    is_speech=True,
                    speech_ms=0,
                    speech_ratio=0.0,
                    error_code="vad_error",
                ),
                audio_bytes,
            )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)


def _serialize_turns(turns: list[TranscriptionTurn]) -> list[dict[str, object]]:
    return [turn.model_dump() for turn in turns]
