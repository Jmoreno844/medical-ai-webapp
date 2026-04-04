from django.db import models
from apps.encounters.models import Encounter
from apps.users.models import User
from apps.templates.models import DoctorTemplate


class Document(models.Model):
    KIND_CHOICES = [
        ("context", "Context"),
        ("transcription", "Transcription"),
        ("template", "Template"),
        ("note", "Note"),
    ]

    encounter = models.ForeignKey(
        Encounter, on_delete=models.CASCADE, related_name="documents"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    doctor_template = models.ForeignKey(
        DoctorTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    content = models.TextField()
    created_on = models.DateField(auto_now_add=True)
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")

    def __str__(self):
        return f"{self.kind} - Encounter {self.encounter_id} - {self.created_on}"
