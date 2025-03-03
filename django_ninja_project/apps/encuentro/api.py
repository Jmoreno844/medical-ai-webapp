from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from ninja.security import django_auth
from .models import Encuentro
from .schemas import (
    EncuentroCreate,
    EncuentroUpdate,
    EncuentroOut,
    EmptyEncuentroResponse,
)
from datetime import date, datetime

router = Router(tags=["encuentros"])


@router.get("/encuentros", response=List[EncuentroOut], auth=django_auth)
def list_encuentros(request):
    # Only return encounters for the authenticated doctor
    encounters = Encuentro.objects.filter(id_medico=request.user.id)

    # Convert each encounter to a dictionary with explicit ID values
    result = []
    for encuentro in encounters:
        result.append(
            {
                "id": encuentro.id,
                "id_medico": encuentro.id_medico.id if encuentro.id_medico else None,
                "id_paciente": encuentro.id_paciente.id
                if encuentro.id_paciente
                else None,
                "paciente_conectado": encuentro.paciente_conectado,
                "nombre_encuentro": encuentro.nombre_encuentro,
                "fecha": encuentro.fecha,
            }
        )
    return result


@router.get("/encuentros/{encuentro_id}", response=EncuentroOut, auth=django_auth)
def get_encuentro(request, encuentro_id: int):
    # Get the encounter or return 404
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede acceder a encuentros de otro médico")

    # Return a dictionary with explicit ID values
    return {
        "id": encuentro.id,
        "id_medico": encuentro.id_medico.id if encuentro.id_medico else None,
        "id_paciente": encuentro.id_paciente.id if encuentro.id_paciente else None,
        "paciente_conectado": encuentro.paciente_conectado,
        "nombre_encuentro": encuentro.nombre_encuentro,
        "fecha": encuentro.fecha,
    }


@router.post("/encuentros", response=EmptyEncuentroResponse, auth=django_auth)
def create_empty_encuentro(request):
    encuentro = Encuentro.objects.create(
        id_medico_id=request.user.id,
        id_paciente_id=None,  # Will be set later
        nombre_encuentro="Encuentro Nuevo",
        fecha=datetime.now(),
    )
    return {"id": encuentro.id}


@router.put("/encuentros/{encuentro_id}", response=EncuentroOut, auth=django_auth)
def update_encuentro(request, encuentro_id: int, payload: EncuentroUpdate):
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede modificar encuentros de otro médico")

    # Get a copy of the payload as dict
    payload_dict = payload.dict(exclude_unset=True)

    # Handle the id_paciente field specially
    if "id_paciente" in payload_dict:
        if payload_dict["id_paciente"] is not None:
            # Get the actual Paciente instance
            from apps.pacientes.models import Paciente

            try:
                paciente = Paciente.objects.get(id=payload_dict["id_paciente"])
                encuentro.id_paciente = paciente
            except Paciente.DoesNotExist:
                raise ValueError(
                    f"Patient with ID {payload_dict['id_paciente']} not found"
                )
        else:
            # Handle setting to None (removing patient)
            encuentro.id_paciente = None

        # Remove from dict so we don't process it again
        del payload_dict["id_paciente"]

    # Update the remaining fields
    for field, value in payload_dict.items():
        setattr(encuentro, field, value)

    encuentro.save()

    # Return a dictionary with explicit ID values, not the model instance
    return {
        "id": encuentro.id,
        "id_medico": encuentro.id_medico.id if encuentro.id_medico else None,
        "id_paciente": encuentro.id_paciente.id if encuentro.id_paciente else None,
        "paciente_conectado": encuentro.paciente_conectado,
        "nombre_encuentro": encuentro.nombre_encuentro,
        "fecha": encuentro.fecha,
    }
