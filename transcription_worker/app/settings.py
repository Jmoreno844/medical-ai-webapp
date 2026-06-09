from __future__ import annotations

from pathlib import Path

from pydantic import Field
from worker_runtime.settings import BaseWorkerSettings


class Settings(BaseWorkerSettings):
    port: int = Field(default=8091, alias="PORT")
    log_level: str = Field(default="INFO", alias="TRANSCRIPTION_WORKER_LOG_LEVEL")
    gcs_bucket_name: str | None = Field(default=None, alias="GCS_BUCKET_NAME")
    transcription_provider: str = Field(
        default="google_genai",
        alias="TRANSCRIPTION_PROVIDER",
    )
    transcription_model: str | None = Field(
        default=None,
        alias="TRANSCRIPTION_MODEL",
    )
    transcription_gemini_model: str = Field(
        default="gemini-2.5-flash",
        alias="TRANSCRIPTION_GEMINI_MODEL",
    )
    transcription_gemini_max_output_tokens: int = Field(
        default=8192,
        alias="TRANSCRIPTION_GEMINI_MAX_OUTPUT_TOKENS",
    )
    silero_model_path: Path = Field(
        default=Path("models/silero_vad.onnx"),
        alias="SILERO_MODEL_PATH",
    )
    ort_intra_op_num_threads: int = Field(default=1, alias="ORT_INTRA_OP_NUM_THREADS")
    vad_max_concurrent: int = Field(default=1, alias="VAD_MAX_CONCURRENT")
    gemini_max_concurrent: int = Field(default=4, alias="GEMINI_MAX_CONCURRENT")
    vad_threshold: float = Field(default=0.5, alias="VAD_THRESHOLD")
    vad_min_speech_ms: int = Field(default=300, alias="VAD_MIN_SPEECH_MS")
    vad_min_speech_ratio: float = Field(default=0.05, alias="VAD_MIN_SPEECH_RATIO")

    @property
    def transcription_provider_name(self) -> str:
        normalized = self.transcription_provider.strip().lower()
        if normalized in {"google", "google_genai", "gemini"}:
            return normalized
        return "google_genai"

    @property
    def effective_transcription_model(self) -> str:
        model = (self.transcription_model or "").strip()
        if model:
            return model
        return self.transcription_gemini_model
