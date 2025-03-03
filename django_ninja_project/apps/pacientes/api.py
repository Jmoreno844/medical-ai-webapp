from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from django.http import HttpRequest
from django.db.models import Q
from .schemas import PacienteCreate, PacienteResponse, PacienteUpdate
from .models import Paciente, PacienteMedico
from apps.users.models import User
from ninja.security import django_auth

router = Router(tags=["pacientes"])


@router.post("/paciente", response=PacienteResponse, auth=django_auth)
def create_paciente(request: HttpRequest, data: PacienteCreate):
    """
    Create a new patient and establish a doctor-patient relationship with the authenticated user.
    Only users with the role 'medico' can create patients.
    """
    # Get the authenticated user (doctor)
    user = request.auth

    # Check if the user has the right role (médico)
    if user.role != "medico":
        return {"detail": "Only doctors can create patients"}, 403

    # Create the patient
    paciente = Paciente.objects.create(nombre=data.nombre, resumen=data.resumen)

    # Create the doctor-patient relationship
    PacienteMedico.objects.create(id_medico=user, id_paciente=paciente)

    return paciente


@router.put("/paciente/{paciente_id}", response=PacienteResponse, auth=django_auth)
def update_paciente(request: HttpRequest, paciente_id: int, data: PacienteUpdate):
    """
    Edit a patient's information.
    Only the doctor associated with the patient can edit their information.
    """
    # Get the authenticated user (doctor)
    user = request.auth

    # Check if the user has the right role
    if user.role != "medico":
        return {"detail": "Only doctors can edit patients"}, 403

    # Get the patient or return 404
    paciente = get_object_or_404(Paciente, id=paciente_id)

    # Check if the doctor is associated with this patient
    relationship_exists = PacienteMedico.objects.filter(
        id_medico=user, id_paciente=paciente
    ).exists()

    if not relationship_exists:
        return {"detail": "You are not authorized to edit this patient"}, 403

    # Update the patient information
    paciente.nombre = data.nombre
    if data.resumen is not None:
        paciente.resumen = data.resumen
    paciente.save()

    return paciente


@router.get("/pacientes/search", response=List[PacienteResponse], auth=django_auth)
def search_pacientes(request: HttpRequest, name: str = ""):
    """
    Search for patients by name.

    This endpoint allows doctors to search for patients by name and only returns
    patients that are associated with the authenticated doctor.

    Args:
        name: The search string to match against patient names

    Returns:
        A list of patients matching the search criteria and associated with the doctor

    Raises:
        403: If the user is not a doctor
    """
    user = request.auth

    # Check if the user has the right role
    if user.role != "medico":
        return {"detail": "Only doctors can search patients"}, 403

    # Get all patients associated with this doctor and matching the search term
    # Using case-insensitive contains lookup
    pacientes = Paciente.objects.filter(
        # Join through the PacienteMedico relationship table
        pacientemedico__id_medico=user,
        # Filter by name containing the search term (case insensitive)
        nombre__icontains=name,
    ).distinct()  # Use distinct to avoid duplicates

    return list(pacientes)
