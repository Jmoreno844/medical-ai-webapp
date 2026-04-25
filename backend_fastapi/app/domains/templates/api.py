from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import DoctorTemplate, TemplateUsage, User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.core.schemas import SuccessResponse
from app.domains.templates.schemas import (
    DoctorTemplateCreate,
    DoctorTemplateListItem,
    DoctorTemplateResponse,
    DoctorTemplateUpdate,
)

router = APIRouter()


def _effective_content(template: DoctorTemplate) -> str | None:
    if template.uses_base_content and template.base_template:
        return template.base_template.content
    return template.content


def _serialize_template(template: DoctorTemplate) -> DoctorTemplateResponse:
    return DoctorTemplateResponse(
        id=template.id,
        name=template.name,
        document_kind=template.document_kind,
        content=_effective_content(template),
        uses_base_content=template.uses_base_content,
        base_template_id=template.base_template_id,
    )


async def _get_template_for_doctor(
    session: AsyncSession,
    *,
    template_id: int,
    doctor_id: int,
) -> DoctorTemplate:
    result = await session.execute(
        select(DoctorTemplate)
        .options(selectinload(DoctorTemplate.base_template))
        .where(DoctorTemplate.id == template_id, DoctorTemplate.doctor_id == doctor_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla no encontrada")
    return template


@router.post("/doctor-templates", response_model=DoctorTemplateResponse)
async def create_doctor_template(
    payload: DoctorTemplateCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorTemplateResponse:
    now = datetime.now(timezone.utc)
    template = DoctorTemplate(
        name=payload.name,
        document_kind=payload.document_kind,
        content=payload.content,
        uses_base_content=False,
        base_template_id=payload.base_template_id,
        created_at=now,
        doctor_id=user.id,
    )
    session.add(template)
    await session.flush()
    session.add(
        TemplateUsage(
            doctor_template_id=template.id,
            doctor_id=user.id,
            use_count=0,
            last_used_at=None,
        )
    )
    await session.commit()
    await session.refresh(template, attribute_names=["base_template"])
    return _serialize_template(template)


@router.get("/doctor-templates/short", response_model=list[DoctorTemplateListItem])
async def list_doctor_templates_short(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[DoctorTemplateListItem]:
    result = await session.execute(
        select(DoctorTemplate, TemplateUsage)
        .outerjoin(
            TemplateUsage,
            (TemplateUsage.doctor_template_id == DoctorTemplate.id)
            & (TemplateUsage.doctor_id == user.id),
        )
        .where(DoctorTemplate.doctor_id == user.id)
        .order_by(DoctorTemplate.name)
    )
    items: list[DoctorTemplateListItem] = []
    for template, usage in result.all():
        items.append(
            DoctorTemplateListItem(
                id=template.id,
                name=template.name,
                document_kind=template.document_kind,
                created_at=template.created_at.isoformat(),
                is_base=template.uses_base_content,
                use_count=usage.use_count if usage else 0,
                last_used_at=usage.last_used_at.isoformat()
                if usage and usage.last_used_at
                else None,
            )
        )
    return items


@router.get("/doctor-templates/{template_id}", response_model=DoctorTemplateResponse)
async def get_doctor_template(
    template_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorTemplateResponse:
    template = await _get_template_for_doctor(
        session,
        template_id=template_id,
        doctor_id=user.id,
    )
    return _serialize_template(template)


@router.patch("/doctor-templates/{template_id}", response_model=DoctorTemplateResponse)
async def update_doctor_template(
    template_id: int,
    payload: DoctorTemplateUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorTemplateResponse:
    template = await _get_template_for_doctor(
        session,
        template_id=template_id,
        doctor_id=user.id,
    )
    template.name = payload.name
    template.document_kind = payload.document_kind
    template.content = payload.content
    await session.commit()
    await session.refresh(template, attribute_names=["base_template"])
    return _serialize_template(template)


@router.post("/doctor-templates/{template_id}/usage", response_model=SuccessResponse)
async def track_template_usage(
    template_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    template = await _get_template_for_doctor(
        session,
        template_id=template_id,
        doctor_id=user.id,
    )
    result = await session.execute(
        select(TemplateUsage).where(
            TemplateUsage.doctor_template_id == template.id,
            TemplateUsage.doctor_id == user.id,
        )
    )
    usage = result.scalar_one_or_none()
    if not usage:
        usage = TemplateUsage(
            doctor_template_id=template.id,
            doctor_id=user.id,
            use_count=0,
            last_used_at=None,
        )
        session.add(usage)
    usage.use_count += 1
    usage.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return SuccessResponse(success=True, message="Template usage tracked successfully")


@router.delete("/doctor-templates/{template_id}", response_model=SuccessResponse)
async def delete_doctor_template(
    template_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    template = await _get_template_for_doctor(
        session,
        template_id=template_id,
        doctor_id=user.id,
    )
    if template.uses_base_content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Base templates cannot be deleted")
    usage_result = await session.execute(
        select(TemplateUsage).where(TemplateUsage.doctor_template_id == template.id)
    )
    for usage in usage_result.scalars().all():
        await session.delete(usage)
    await session.delete(template)
    await session.commit()
    return SuccessResponse(success=True, message="Template deleted successfully")

