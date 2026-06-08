from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth import verify_cloud_tasks_request
from app.audio import decode_audio_to_float32_pcm
from app.debug_cuts import build_worker_debug_cut
from app.logging_config import configure_logging
from app.tracing import configure_tracing
from app.processor import Processor
from app.settings import Settings
from app.gemini import transcribe_audio
from app.text_filters import normalize_transcript

settings = Settings()
configure_logging(settings, service_name="vexthealth-transcription-worker")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VextHealth Transcription Worker",
    version="0.1.0",
    docs_url="/api/v1/docs" if settings.is_local else None,
    openapi_url="/api/v1/openapi.json" if settings.is_local else None,
)
configure_tracing(
    app,
    settings,
    service_name="vexthealth-transcription-worker",
)
if settings.is_local:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
processor = Processor.create(settings)


class EmptyPayload(BaseModel):
    pass


class DebugTranscriptionResponse(BaseModel):
    success: bool
    mode: str = "transcribe"
    provider: str
    model: str
    transcript: str
    content_type: str
    vad_decision: str
    vad_speech_ms: int
    vad_speech_ratio: float
    vad_error_code: str | None = None


class DebugSpeechIntervalResponse(BaseModel):
    start_ms: int
    end_ms: int


class DebugFrontendCutResponse(BaseModel):
    section_duration_ms: int
    speech_duration_ms: int
    speech_frame_count: int
    has_detected_speech: bool
    cut_reason: str
    overlap_ms: int
    speech_intervals: list[DebugSpeechIntervalResponse]
    removable_silences: list[DebugSpeechIntervalResponse]
    retained_intervals: list[DebugSpeechIntervalResponse]


class DebugWorkerCutResponse(BaseModel):
    original_duration_ms: int
    retained_duration_ms: int
    speech_duration_ms: int
    speech_ratio: float
    retained_intervals: list[DebugSpeechIntervalResponse]
    removable_silences: list[DebugSpeechIntervalResponse]
    speech_intervals: list[DebugSpeechIntervalResponse]
    trim_applied: bool


class DebugWorkerInputResponse(BaseModel):
    input_byte_size: int
    decoded_sample_count: int
    decoded_duration_ms: int
    sample_rate_hz: int
    trimmed_audio_byte_size: int


class DebugCutComparisonResponse(BaseModel):
    original_duration_ms: int
    frontend_retained_duration_ms: int
    worker_retained_duration_ms: int
    retained_duration_delta_ms: int
    frontend_removed_silence_ms: int
    worker_removed_silence_ms: int
    silence_removed_delta_ms: int


class DebugTranscriptionComparisonResponse(DebugTranscriptionResponse):
    frontend_cut: DebugFrontendCutResponse
    worker_input: DebugWorkerInputResponse
    worker_cut: DebugWorkerCutResponse
    comparison: DebugCutComparisonResponse


def get_processor() -> Processor:
    return processor


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "transcription-worker"}


@app.post("/api/v1/internal/transcription/tasks/sections/{section_id}")
async def run_section_task(
    section_id: str,
    request: Request,
    _payload: EmptyPayload | None = None,
    worker: Processor = Depends(get_processor),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    await worker.process_section(section_id)
    return {"success": True}


@app.post(
    "/api/v1/dev/transcription/debug",
    response_model=DebugTranscriptionComparisonResponse,
)
async def debug_transcription(
    file: UploadFile = File(...),
    mode: str = Form(default="transcribe"),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    frontend_cut_json: str | None = Form(default=None),
    worker: Processor = Depends(get_processor),
) -> DebugTranscriptionComparisonResponse:
    if not settings.is_local:
        raise HTTPException(status_code=404, detail="Not found")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    effective_settings = settings.model_copy(
        update={
            "transcription_provider": provider or settings.transcription_provider,
            "transcription_model": model or settings.transcription_model,
        }
    )
    frontend_cut = _parse_frontend_cut(frontend_cut_json)
    audio_samples = decode_audio_to_float32_pcm(audio_bytes)
    decoded_duration_ms = int(round((len(audio_samples) / 16000) * 1000))
    vad_result, worker_cut, trimmed_audio_bytes = build_worker_debug_cut(
        audio_samples,
        effective_settings,
    )
    vad_decision = "speech"
    transcript = ""

    if not vad_result.is_speech and vad_result.error_code is None:
        vad_decision = "no_speech"
    elif vad_result.error_code is not None:
        vad_decision = "fail_open"
    elif mode == "vad_only":
        vad_decision = "speech"
    else:
        async with worker.gemini_semaphore:
            transcript = await transcribe_audio(
                gcs_uri=None,
                content_type="audio/wav",
                settings=effective_settings,
                audio_bytes=trimmed_audio_bytes,
            )
        transcript = normalize_transcript(transcript)

    comparison = _build_cut_comparison(frontend_cut, worker_cut)
    return DebugTranscriptionComparisonResponse(
        success=True,
        mode=mode,
        provider=effective_settings.transcription_provider_name,
        model=effective_settings.effective_transcription_model,
        transcript=transcript,
        content_type=file.content_type or "audio/webm",
        vad_decision=vad_decision,
        vad_speech_ms=vad_result.speech_ms,
        vad_speech_ratio=vad_result.speech_ratio,
        vad_error_code=vad_result.error_code,
        frontend_cut=frontend_cut,
        worker_input=DebugWorkerInputResponse(
            input_byte_size=len(audio_bytes),
            decoded_sample_count=len(audio_samples),
            decoded_duration_ms=decoded_duration_ms,
            sample_rate_hz=16000,
            trimmed_audio_byte_size=len(trimmed_audio_bytes),
        ),
        worker_cut=_serialize_worker_cut(worker_cut),
        comparison=comparison,
    )


@app.post("/api/v1/dev/transcription/debug/trimmed-audio")
async def debug_trimmed_audio(
    file: UploadFile = File(...),
    worker: Processor = Depends(get_processor),
) -> Response:
    del worker  # debug endpoint only needs the local audio/VAD pipeline

    if not settings.is_local:
        raise HTTPException(status_code=404, detail="Not found")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    audio_samples = decode_audio_to_float32_pcm(audio_bytes)
    _vad_result, _worker_cut, trimmed_audio_bytes = build_worker_debug_cut(
        audio_samples,
        settings,
    )
    return Response(
        content=trimmed_audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": 'inline; filename="worker-trimmed-preview.wav"'
        },
    )


def _parse_frontend_cut(frontend_cut_json: str | None) -> DebugFrontendCutResponse:
    if not frontend_cut_json:
        return DebugFrontendCutResponse(
            section_duration_ms=0,
            speech_duration_ms=0,
            speech_frame_count=0,
            has_detected_speech=False,
            cut_reason="unknown",
            overlap_ms=0,
            speech_intervals=[],
            removable_silences=[],
            retained_intervals=[],
        )
    return DebugFrontendCutResponse.model_validate_json(frontend_cut_json)


def _serialize_worker_cut(worker_cut) -> DebugWorkerCutResponse:
    return DebugWorkerCutResponse(
        original_duration_ms=worker_cut.original_duration_ms,
        retained_duration_ms=worker_cut.retained_duration_ms,
        speech_duration_ms=worker_cut.speech_duration_ms,
        speech_ratio=worker_cut.speech_ratio,
        retained_intervals=[
            DebugSpeechIntervalResponse(
                start_ms=interval.start_ms,
                end_ms=interval.end_ms,
            )
            for interval in worker_cut.retained_intervals
        ],
        removable_silences=[
            DebugSpeechIntervalResponse(
                start_ms=interval.start_ms,
                end_ms=interval.end_ms,
            )
            for interval in worker_cut.removable_silences
        ],
        speech_intervals=[
            DebugSpeechIntervalResponse(
                start_ms=interval.start_ms,
                end_ms=interval.end_ms,
            )
            for interval in worker_cut.speech_intervals
        ],
        trim_applied=worker_cut.trim_applied,
    )


def _build_cut_comparison(
    frontend_cut: DebugFrontendCutResponse,
    worker_cut,
) -> DebugCutComparisonResponse:
    frontend_removed_silence_ms = sum(
        interval.end_ms - interval.start_ms for interval in frontend_cut.removable_silences
    )
    worker_removed_silence_ms = sum(
        interval.end_ms - interval.start_ms for interval in worker_cut.removable_silences
    )
    frontend_retained_duration_ms = sum(
        interval.end_ms - interval.start_ms for interval in frontend_cut.retained_intervals
    ) or frontend_cut.section_duration_ms
    return DebugCutComparisonResponse(
        original_duration_ms=worker_cut.original_duration_ms,
        frontend_retained_duration_ms=frontend_retained_duration_ms,
        worker_retained_duration_ms=worker_cut.retained_duration_ms,
        retained_duration_delta_ms=(
            worker_cut.retained_duration_ms - frontend_retained_duration_ms
        ),
        frontend_removed_silence_ms=frontend_removed_silence_ms,
        worker_removed_silence_ms=worker_removed_silence_ms,
        silence_removed_delta_ms=worker_removed_silence_ms - frontend_removed_silence_ms,
    )
