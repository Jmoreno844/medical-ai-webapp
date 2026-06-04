from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    port: int = Field(default=8091, alias="PORT")
    log_level: str = Field(default="INFO", alias="TRANSCRIPTION_WORKER_LOG_LEVEL")

    backend_internal_base_url: str = Field(
        default="http://localhost:8001",
        alias="BACKEND_INTERNAL_BASE_URL",
    )
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="us-east1", alias="GCP_REGION")
    vertex_ai_location: str = Field(default="global", alias="VERTEX_AI_LOCATION")
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
    transcription_openai_model: str = Field(
        default="gpt-4o-mini-transcribe",
        alias="TRANSCRIPTION_OPENAI_MODEL",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    cloud_tasks_invoker_service_account: str | None = Field(
        default=None,
        alias="CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT",
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
    def is_local(self) -> bool:
        return self.environment.strip().lower() in {"local", "dev", "develop", "test"}

    @property
    def transcription_provider_name(self) -> str:
        return self.transcription_provider.strip().lower()

    @property
    def effective_transcription_model(self) -> str:
        model = (self.transcription_model or "").strip()
        if model:
            return model
        if self.transcription_provider_name in {"openai", "openai_api"}:
            return self.transcription_openai_model
        return self.transcription_gemini_model
