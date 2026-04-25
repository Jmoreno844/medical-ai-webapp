from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, Encounter
from app.domains.documents.content import (
    build_synced_document_content,
    set_document_content_fields,
)
from app.domains.documents.schemas import DocumentContentUpdate, DocumentCreate, DocumentOut


async def get_document_for_doctor(
    session: AsyncSession,
    *,
    document_id: int,
    doctor_id: int,
) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def get_encounter_for_doctor(
    session: AsyncSession,
    *,
    encounter_id: int,
    doctor_id: int,
) -> Encounter | None:
    result = await session.execute(
        select(Encounter).where(
            Encounter.id == encounter_id,
            Encounter.doctor_id == doctor_id,
        )
    )
    return result.scalar_one_or_none()


def serialize_document(doc: Document) -> DocumentOut:
    doctor_template = doc.doctor_template
    return DocumentOut(
        id=doc.id,
        encounter_id=doc.encounter_id,
        kind=doc.kind,
        doctor_template_id=doc.doctor_template_id,
        doctor_template_name=doctor_template.name if doctor_template else None,
        content=doc.content_markdown,
        content_markdown=doc.content_markdown,
        content_json=doc.content_json,
        doctor_id=doc.doctor_id,
        created_on=doc.created_on,
    )


def resolve_payload_markdown(payload: DocumentCreate | DocumentContentUpdate) -> str:
    if payload.content_markdown is not None:
        return payload.content_markdown
    if payload.content is not None:
        return payload.content
    return ""


def resolve_payload_json(
    payload: DocumentCreate | DocumentContentUpdate,
) -> dict[str, Any] | None:
    return payload.content_json


def editor_payload_source(
    payload: DocumentCreate | DocumentContentUpdate,
) -> str:
    if payload.content_json is not None:
        return "json"
    return "markdown"


async def list_documents_for_encounter(
    session: AsyncSession,
    *,
    encounter_id: int,
    doctor_id: int,
) -> list[Document]:
    encounter = await get_encounter_for_doctor(
        session,
        encounter_id=encounter_id,
        doctor_id=doctor_id,
    )
    if not encounter:
        return []

    result = await session.execute(
        select(Document)
        .options(selectinload(Document.doctor_template))
        .where(Document.encounter_id == encounter_id)
        .order_by(Document.id)
    )
    return list(result.scalars().all())


async def create_document(
    session: AsyncSession,
    *,
    payload: DocumentCreate,
    doctor_id: int,
) -> Document:
    encounter = await get_encounter_for_doctor(
        session,
        encounter_id=payload.encounter_id,
        doctor_id=doctor_id,
    )
    if not encounter:
        raise ValueError("Encuentro no encontrado")

    if payload.kind not in {"context", "transcription", "template", "note"}:
        raise ValueError("Tipo de documento inválido")
    if payload.kind == "template" and payload.doctor_template_id is None:
        raise ValueError("Se requiere doctor_template_id cuando el kind es 'template'")

    synced_content = build_synced_document_content(
        content_markdown=resolve_payload_markdown(payload),
        content_json=resolve_payload_json(payload),
        preferred_source=editor_payload_source(payload),  # type: ignore[arg-type]
    )
    document = Document(
        encounter_id=payload.encounter_id,
        doctor_id=doctor_id,
        doctor_template_id=payload.doctor_template_id
        if payload.kind == "template"
        else None,
        kind=payload.kind,
        content_markdown=synced_content.content_markdown,
        content_json=synced_content.content_json,
        created_on=date.today(),
    )
    session.add(document)
    await session.flush()
    await session.refresh(document, attribute_names=["doctor_template"])
    return document


async def update_document_content(
    session: AsyncSession,
    *,
    document_id: int,
    doctor_id: int,
    payload: DocumentContentUpdate,
) -> Document | None:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=doctor_id,
    )
    if not document:
        return None
    set_document_content_fields(
        document,
        content_markdown=resolve_payload_markdown(payload),
        content_json=resolve_payload_json(payload),
        preferred_source=editor_payload_source(payload),  # type: ignore[arg-type]
    )
    await session.flush()
    return document


def new_empty_document(*, encounter_id: int, doctor_id: int, kind: str) -> Document:
    synced_content = build_synced_document_content()
    return Document(
        encounter_id=encounter_id,
        doctor_id=doctor_id,
        doctor_template_id=None,
        kind=kind,
        content_markdown=synced_content.content_markdown,
        content_json=synced_content.content_json,
        created_on=date.today(),
    )
