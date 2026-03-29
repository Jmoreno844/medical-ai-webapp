from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from ninja.security import django_auth
from django.db.models import F
from ninja.errors import HttpError
from django.utils import timezone
from .models import BaseTemplate, DoctorTemplate, TemplateUsage
from .schemas import (
    DoctorTemplateCreate,
    DoctorTemplateResponse,
    DoctorTemplateListItem,
    DoctorTemplateUpdate,
)

router = Router(tags=["templates"])


@router.post("/doctor-templates", response=DoctorTemplateResponse, auth=django_auth)
def create_doctor_template(request, data: DoctorTemplateCreate):
    dt = DoctorTemplate(
        name=data.name,
        document_kind=data.document_kind,
        content=data.content,
        uses_base_content=False,
        doctor=request.user,
        base_template_id=data.base_template_id,
    )

    dt.save()

    TemplateUsage.objects.create(
        doctor_template=dt,
        doctor=request.user,
        use_count=0,
        last_used_at=None,
    )

    return {
        "id": dt.id,
        "name": dt.name,
        "document_kind": dt.document_kind,
        "content": dt.content,
        "uses_base_content": dt.uses_base_content,
        "base_template_id": dt.base_template_id,
    }


@router.get("/doctor-templates/short", response=List[DoctorTemplateListItem], auth=django_auth)
def list_doctor_templates_short(request):
    user = request.user

    templates = DoctorTemplate.objects.filter(doctor=user).order_by("name")

    result = []
    for t in templates:
        try:
            usage = TemplateUsage.objects.get(doctor_template=t, doctor=user)
            use_count = usage.use_count
            last_used_at = usage.last_used_at.isoformat() if usage.last_used_at else None
        except TemplateUsage.DoesNotExist:
            use_count = 0
            last_used_at = None

        result.append(
            {
                "id": t.id,
                "name": t.name,
                "document_kind": t.document_kind,
                "created_at": t.created_at.isoformat(),
                "is_base": t.uses_base_content,
                "use_count": use_count,
                "last_used_at": last_used_at,
            }
        )

    return result


@router.get(
    "/doctor-templates/{template_id}",
    response=DoctorTemplateResponse,
    auth=django_auth,
)
def get_doctor_template(request, template_id: int):
    user = request.user

    t = get_object_or_404(DoctorTemplate, id=template_id, doctor=user)

    content = t.get_effective_content()

    return {
        "id": t.id,
        "name": t.name,
        "document_kind": t.document_kind,
        "content": content,
        "uses_base_content": t.uses_base_content,
        "base_template_id": t.base_template_id,
    }


@router.patch(
    "/doctor-templates/{template_id}",
    response=DoctorTemplateResponse,
    auth=django_auth,
)
def update_doctor_template(request, template_id: int, data: DoctorTemplateUpdate):
    t = get_object_or_404(DoctorTemplate, id=template_id)

    if request.user.id != t.doctor.id:
        raise HttpError(403, "You don't have permission to update this template")

    t.name = data.name
    t.document_kind = data.document_kind
    t.content = data.content
    t.save()

    return {
        "id": t.id,
        "name": t.name,
        "document_kind": t.document_kind,
        "content": t.content,
        "uses_base_content": t.uses_base_content,
        "base_template_id": t.base_template_id,
    }


@router.post("/doctor-templates/{template_id}/usage", auth=django_auth)
def track_template_usage(request, template_id: int):
    t = get_object_or_404(DoctorTemplate, id=template_id)

    if request.user.id != t.doctor.id:
        raise HttpError(
            403, "You don't have permission to track usage for this template"
        )

    usage = TemplateUsage.objects.get(doctor_template=t, doctor=request.user)
    usage.use_count = F("use_count") + 1
    usage.last_used_at = timezone.now()
    usage.save()

    return {"success": True, "message": "Template usage tracked successfully"}


@router.delete("/doctor-templates/{template_id}", auth=django_auth)
def delete_doctor_template(request, template_id: int):
    t = get_object_or_404(DoctorTemplate, id=template_id)

    if request.user.id != t.doctor.id:
        raise HttpError(403, "You don't have permission to delete this template")

    if t.uses_base_content:
        raise HttpError(400, "Base templates cannot be deleted")

    TemplateUsage.objects.filter(doctor_template=t).delete()

    t.delete()

    return {"success": True, "message": "Template deleted successfully"}
