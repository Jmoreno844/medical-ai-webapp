from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    encounter_id: int
    kind: str
    doctor_template_id: int | None = None
    content: str | None = ""
    content_markdown: str | None = None
    content_json: dict[str, Any] | None = None


class DocumentOut(BaseModel):
    id: int
    encounter_id: int
    kind: str
    doctor_template_id: int | None
    doctor_template_name: str | None = None
    content: str
    content_markdown: str
    content_json: dict[str, Any] | None = None
    created_on: date
    doctor_id: int


class DocumentContentUpdate(BaseModel):
    content: str | None = None
    content_markdown: str | None = None
    content_json: dict[str, Any] | None = None


class DocumentContentOut(BaseModel):
    content: str
    content_markdown: str
    content_json: dict[str, Any] | None = None


class DocumentGenerationWorkflowRequest(BaseModel):
    context_document_id: int
    transcription_document_id: int
    doctor_template_id: int
    new_document_id: int


class DocumentGenerationWorkflowResponse(BaseModel):
    success: bool
    process_id: str | None = None
    sse_token: str | None = None
    new_document_id: int | None = None
    message: str | None = None
    error: str | None = None


class GenerationChunkIn(BaseModel):
    document_id: int
    process_id: str
    chunk: str | None = ""
    is_complete: bool = False
    is_error: bool = False
    error: str | None = None
    is_progress: bool = False
    pipeline_step: str | None = None
    append: bool = False


class TranscriptionTurnWithId(BaseModel):
    turn_id: int
    speaker: str
    text: str


class StepGuidelinesOut(BaseModel):
    guidelines: str = ""


class TemplateSectionOut(BaseModel):
    section_id: str
    heading: str
    description: str = ""
    classification: StepGuidelinesOut = Field(default_factory=StepGuidelinesOut)
    generation: StepGuidelinesOut = Field(default_factory=StepGuidelinesOut)


class ClinicalTemplateOut(BaseModel):
    id: str
    name: str
    document_kind: str = "document"
    classification: StepGuidelinesOut = Field(default_factory=StepGuidelinesOut)
    generation: StepGuidelinesOut = Field(default_factory=StepGuidelinesOut)
    sections: list[TemplateSectionOut] = Field(default_factory=list)


class ExternalDocumentInputOut(BaseModel):
    document_id: str
    document_kind: str = "document"
    document_date: str | None = None
    content_markdown: str | None = None
    content_pdf_gcs_uri: str | None = None


class ContextInputsOut(BaseModel):
    doctor_note_markdown: str | None = None
    external_documents: list[ExternalDocumentInputOut] = Field(default_factory=list)


class DocumentGenerationTaskPayload(BaseModel):
    process_id: str
    doctor_id: int
    new_document_id: int
    context_document_id: int
    transcription_document_id: int
    doctor_template_id: int


class DocumentGenerationWorkItemResponse(BaseModel):
    process_id: str
    doctor_id: int
    new_document_id: int
    context_document_id: int
    transcription_document_id: int
    doctor_template_id: int
    encounter_id: int
    context_inputs: ContextInputsOut
    context_content: str
    transcription_content: str
    template_content: str
    transcription_turns: list[TranscriptionTurnWithId]
    template: ClinicalTemplateOut
    callback_token: str


class TranscriptionNotificationIn(BaseModel):
    document_id: int
    status: str | None = None
