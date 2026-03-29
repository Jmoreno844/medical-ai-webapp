from django.db import models
from apps.users.models import User


class Patient(models.Model):
    name = models.CharField(max_length=255)
    summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PatientDoctor(models.Model):
    doctor = models.ForeignKey(User, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("doctor", "patient")
        indexes = [
            models.Index(fields=["doctor"]),
            models.Index(fields=["patient"]),
        ]

    def __str__(self):
        return f"{self.patient.name} - {self.doctor.get_full_name()}"
