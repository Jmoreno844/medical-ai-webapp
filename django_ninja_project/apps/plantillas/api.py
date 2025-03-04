from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from ninja.security import django_auth
from .models import PlantillaBase, PlantillaDoctor
from .schemas import (
    PlantillaDoctorCreate,
    PlantillaDoctorResponse,
    PlantillaDoctorListItem,
)

router = Router(tags=["plantillas"])


@router.post("/plantilla_doctor", response=PlantillaDoctorResponse, auth=django_auth)
def create_plantilla_doctor(request, data: PlantillaDoctorCreate):
    """
    Create a new doctor-specific template.

    This endpoint allows authenticated doctors to create their own templates.
    The doctor ID is automatically obtained from the authenticated user.
    The 'contenido_base' is set to false by default, meaning the template will use its own content.

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
    }


@router.get(
    "/plantilla_doctor", response=List[PlantillaDoctorListItem], auth=django_auth
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
        result.append(
            {
                "id": plantilla.id,
                "nombre": plantilla.nombre,
                "tipo_documento": plantilla.tipo_documento,
            }
        )

    return result
