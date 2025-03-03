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
from datetime import date

router = Router(tags=["encuentros"])


@router.get("/encuentros", response=List[EncuentroOut], auth=django_auth)
def list_encuentros(request):
    # Only return encounters for the authenticated doctor
    return Encuentro.objects.filter(id_medico=request.user.id)


@router.get("/encuentros/{encuentro_id}", response=EncuentroOut, auth=django_auth)
def get_encuentro(request, encuentro_id: int):
    # Get the encounter or return 404
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede acceder a encuentros de otro médico")

    return encuentro


@router.post("/encuentros", response=EmptyEncuentroResponse, auth=django_auth)
def create_empty_encuentro(request):
    encuentro = Encuentro.objects.create(
        id_medico_id=request.user.id,
        id_paciente_id=None,  # Will be set later
        nombre_encuentro="Encuentro Nuevo",
        fecha=date.today(),
    )
    return {"id": encuentro.id}


@router.put("/encuentros/{encuentro_id}", response=EncuentroOut, auth=django_auth)
def update_encuentro(request, encuentro_id: int, payload: EncuentroUpdate):
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede modificar encuentros de otro médico")

    # Update the encounter fields
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(encuentro, field, value)

    encuentro.save()
    return encuentro
