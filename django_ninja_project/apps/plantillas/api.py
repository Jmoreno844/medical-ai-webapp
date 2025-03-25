from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from ninja.security import django_auth
from django.db.models import F
from ninja.errors import HttpError
from django.utils import timezone
from .models import PlantillaBase, PlantillaDoctor, UsoPlantilla
from .schemas import (
    PlantillaDoctorCreate,
    PlantillaDoctorResponse,
    PlantillaDoctorListItem,
    PlantillaDoctorUpdate,
)

router = Router(tags=["plantillas"])


@router.post("/plantilla_doctor", response=PlantillaDoctorResponse, auth=django_auth)
def create_plantilla_doctor(request, data: PlantillaDoctorCreate):
    """
    Create a new doctor-specific template.

    This endpoint allows authenticated doctors to create their own templates.
    The doctor ID is automatically obtained from the authenticated user.
    The 'contenido_base' is set to false by default, meaning the template will use its own content.

    Also creates a usage tracking entry for the template.

    Args:
        data: Template data including name, type, and content

    Returns:
        The created template with all its attributes
    """
    # Create the new template with contenido_base=False
    plantilla_doctor = PlantillaDoctor(
        nombre=data.nombre,
        tipo_documento=data.tipo_documento,
        contenido=data.contenido,
        contenido_base=False,  # Always set to False for this endpoint
        id_medico=request.user,  # Get the doctor ID from the authenticated user
        id_plantilla_base=None,
    )

    # If a base template ID was provided, link it

    # Save the template
    plantilla_doctor.save()

    # Create usage tracking entry
    uso_plantilla = UsoPlantilla(
        id_plantilla=plantilla_doctor,
        id_medico=request.user,
        veces_usada=0,  # Initialize with zero uses
        ultimo_uso=None,  # No usage yet
    )
    uso_plantilla.save()

    # Return the created template
    return {
        "id": plantilla_doctor.id,
        "nombre": plantilla_doctor.nombre,
        "tipo_documento": plantilla_doctor.tipo_documento,
        "contenido": plantilla_doctor.contenido,
        "contenido_base": plantilla_doctor.contenido_base,
        "id_plantilla_base": plantilla_doctor.id_plantilla_base.id
        if plantilla_doctor.id_plantilla_base
        else None,
        "fecha_creacion": plantilla_doctor.fecha_creacion.isoformat(),
        "veces_usada": 0,  # New template has not been used yet
        "ultimo_uso": None,
    }


@router.get(
    "/plantillas_short", response=List[PlantillaDoctorListItem], auth=django_auth
)
def list_plantillas_doctor(request):
    """
    Fetch all templates for the authenticated doctor.

    Returns only the ID, name, and document type for each template.
    Templates are sorted by name.

    Returns:
        A list of doctor-specific templates with minimal information
    """
    # Get the authenticated user
    user = request.user

    # Query templates associated with this doctor
    plantillas = PlantillaDoctor.objects.filter(id_medico=user).order_by("nombre")

    # Transform to response format with only the requested fields
    result = []
    for plantilla in plantillas:
        # Try to get usage statistics, or default to zeros
        try:
            uso = UsoPlantilla.objects.get(id_plantilla=plantilla, id_medico=user)
            veces_usada = uso.veces_usada
            ultimo_uso = uso.ultimo_uso.isoformat() if uso.ultimo_uso else None
        except UsoPlantilla.DoesNotExist:
            veces_usada = 0
            ultimo_uso = None

        result.append(
            {
                "id": plantilla.id,
                "nombre": plantilla.nombre,
                "tipo_documento": plantilla.tipo_documento,
                "fecha_creacion": plantilla.fecha_creacion.isoformat(),
                "es_base": plantilla.contenido_base,
                "veces_usada": veces_usada,
                "ultimo_uso": ultimo_uso,
            }
        )

    return result


@router.get(
    "/plantilla_doctor/{id_plantilla}",
    response=PlantillaDoctorResponse,
    auth=django_auth,
)
def get_plantilla_doctor(request, id_plantilla: int):
    """
    Get details for a specific doctor's template including usage statistics.

    Args:
        id_plantilla: The template ID to retrieve

    Returns:
        Complete template details including usage information
    """
    # Get the authenticated user
    user = request.user

    # Get the template
    plantilla = get_object_or_404(PlantillaDoctor, id=id_plantilla, id_medico=user)

    # Get the effective content - from base template if contenido_base is True
    contenido = plantilla.get_contenido_efectivo()

    # Return the template with usage information
    return {
        "id": plantilla.id,
        "nombre": plantilla.nombre,
        "tipo_documento": plantilla.tipo_documento,
        "contenido": contenido,
        "contenido_base": plantilla.contenido_base,
        "id_plantilla_base": plantilla.id_plantilla_base.id
        if plantilla.id_plantilla_base
        else None,
    }


@router.patch(
    "/plantilla_doctor/{id_plantilla}",
    response=PlantillaDoctorResponse,
    auth=django_auth,
)
def update_plantilla_doctor(request, id_plantilla: int, data: PlantillaDoctorUpdate):
    """
    Update a doctor's template

    Args:
        request: The HTTP request
        id_plantilla: The ID of the template to update
        data: The update data

    Returns:
        The updated template

    Raises:
        HttpError: If the user is not authorized or the template is not found
    """
    # Get the template or return 404
    plantilla = get_object_or_404(PlantillaDoctor, id=id_plantilla)

    # Check authorization - make sure the requesting user is the template owner
    if request.user.id != plantilla.id_medico.id:
        raise HttpError(403, "You don't have permission to update this template")

    # Update the template fields
    plantilla.nombre = data.nombre
    plantilla.tipo_documento = data.tipo_documento
    plantilla.contenido = data.contenido
    plantilla.save()

    # Return the updated template
    return {
        "id": plantilla.id,
        "nombre": plantilla.nombre,
        "tipo_documento": plantilla.tipo_documento,
        "contenido": plantilla.contenido,
        "contenido_base": plantilla.contenido_base,
        "id_plantilla_base": plantilla.id_plantilla_base.id
        if plantilla.id_plantilla_base
        else None,
    }


@router.post("/plantilla_doctor/uso/{id_plantilla}", auth=django_auth)
def track_plantilla_usage(request, id_plantilla: int):
    """
    Track the usage of a doctor's template

    Args:
        request: The HTTP request
        id_plantilla: The ID of the template to track

    Returns:
        A simple success response

    Raises:
        HttpError: If the user is not authorized or the template is not found
    """
    # Get the template or return 404
    plantilla = get_object_or_404(PlantillaDoctor, id=id_plantilla)

    # Check authorization - make sure the requesting user is the template owner
    if request.user.id != plantilla.id_medico.id:
        raise HttpError(
            403, "You don't have permission to track usage for this template"
        )

    # Update the usage tracking entry
    uso_plantilla = UsoPlantilla.objects.get(
        id_plantilla=plantilla, id_medico=request.user
    )
    uso_plantilla.veces_usada = F("veces_usada") + 1
    uso_plantilla.ultimo_uso = timezone.now()
    uso_plantilla.save()

    # Return a simple success response
    return {"success": True, "message": "Template usage tracked successfully"}
