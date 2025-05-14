import pytest
from django.urls import reverse
from datetime import date
from apps.medico.models import Medico
from apps.paciente.models import Paciente
from .models import Encuentro


@pytest.fixture
def medico(db):
    return Medico.objects.create(
        email="test@doctor.com",
        password="testpass123",
        nombre="Dr. Test",
        especialidad="General",
    )


@pytest.fixture
def otro_medico(db):
    return Medico.objects.create(
        email="other@doctor.com",
        password="testpass123",
        nombre="Dr. Other",
        especialidad="General",
    )


@pytest.fixture
def paciente(db):
    return Paciente.objects.create(
        email="patient@test.com", nombre="Test Patient", fecha_nacimiento="1990-01-01"
    )


@pytest.fixture
def encuentro(db, medico, paciente):
    return Encuentro.objects.create(
        id_medico=medico,
        id_paciente=paciente,
        nombre_encuentro="Test Encuentro",
        fecha=date.today(),
    )


@pytest.mark.django_db
class TestEncuentroAPI:
    def test_list_encuentros(self, client, medico, encuentro):
        # Create an encounter for another doctor to ensure it's not returned
        otro_encuentro = Encuentro.objects.create(
            id_medico=otro_medico,
            id_paciente=paciente,
            nombre_encuentro="Other Encuentro",
            fecha=date.today(),
        )

        response = client.get(
            "/api/encuentros", HTTP_AUTHORIZATION=f"Bearer {medico.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == encuentro.id
        assert data[0]["id_medico"] == medico.id

    def test_create_encuentro(self, client, medico, paciente):
        payload = {
            "id_medico": medico.id,
            "id_paciente": paciente.id,
            "nombre_encuentro": "New Encuentro",
            "fecha": str(date.today()),
        }

        response = client.post(
            "/api/encuentros",
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {medico.id}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nombre_encuentro"] == "New Encuentro"
        assert data["id_medico"] == medico.id
        assert data["id_paciente"] == paciente.id

    def test_create_encuentro_unauthorized(self, client, medico, otro_medico, paciente):
        payload = {
            "id_medico": otro_medico.id,  # Trying to create for another doctor
            "id_paciente": paciente.id,
            "nombre_encuentro": "Unauthorized Encuentro",
            "fecha": str(date.today()),
        }

        response = client.post(
            "/api/encuentros",
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {medico.id}",
        )

        assert response.status_code == 403

    def test_create_empty_encuentro(self, client, medico):
        response = client.post(
            "/api/encuentros/new", HTTP_AUTHORIZATION=f"Bearer {medico.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        # Verify the encounter was created with correct defaults
        encuentro = Encuentro.objects.get(id=data["id"])
        assert encuentro.id_medico_id == medico.id
        assert encuentro.id_paciente_id is None
        assert encuentro.nombre_encuentro == "Encuentro Nuevo"
        assert encuentro.fecha == date.today()
