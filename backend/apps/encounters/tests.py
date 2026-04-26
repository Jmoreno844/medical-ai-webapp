import pytest
from datetime import datetime

from apps.encounters.models import Encounter
from apps.patients.models import Patient, PatientDoctor
from apps.users.models import User


@pytest.fixture
def doctor(db):
    user = User.objects.create(
        email="test@doctor.com",
        name="Dr.",
        last_name="Test",
    )
    user.set_password("testpass123")
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def other_doctor(db):
    user = User.objects.create(
        email="other@doctor.com",
        name="Dr.",
        last_name="Other",
    )
    user.set_password("testpass123")
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def paciente(db):
    return Patient.objects.create(name="Test Patient")


@pytest.fixture
def encounter(db, doctor, paciente):
    PatientDoctor.objects.create(doctor=doctor, patient=paciente)
    return Encounter.objects.create(
        doctor=doctor,
        patient=paciente,
        encounter_name="Test Encounter",
        occurred_at=datetime.now(),
    )


@pytest.mark.django_db
class TestEncounterAPI:
    def test_list_encounters(self, client, doctor, other_doctor, paciente, encounter):
        client.force_login(doctor)
        Encounter.objects.create(
            doctor=other_doctor,
            patient=paciente,
            encounter_name="Other Encounter",
            occurred_at=datetime.now(),
        )

        response = client.get("/api/encounters")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == encounter.id
        assert data[0]["doctor_id"] == doctor.id

    def test_create_empty_encounter(self, client, doctor):
        client.force_login(doctor)

        response = client.post("/api/encounters", data={}, content_type="application/json")

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        encounter = Encounter.objects.get(id=data["id"])
        assert encounter.doctor_id == doctor.id
        assert encounter.patient_id is None
        assert encounter.encounter_name == "Encuentro Nuevo"
