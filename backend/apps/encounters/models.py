from django.db import models
from apps.users.models import User
from apps.patients.models import Patient


class Encounter(models.Model):
    doctor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="encounters"
    )
    patient_connected = models.BooleanField(default=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="encounters",
        null=True,
        blank=True,
    )
    encounter_name = models.CharField(max_length=255, null=True, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    audio_file_name = models.CharField(max_length=255, null=True, blank=True)
    audio_uploaded_at = models.DateTimeField(null=True, blank=True)
    audio_expires_at = models.DateTimeField(null=True, blank=True)
    audio_duration_seconds = models.IntegerField(null=True, blank=True)
    has_been_transcribed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["doctor"]),
            models.Index(fields=["patient"]),
        ]

    def __str__(self):
        return f"Encounter {self.id} - {self.occurred_at}"

    def save(self, *args, **kwargs):
        if self.audio_file_name and not self.audio_uploaded_at:
            from django.utils import timezone
            import datetime

            self.audio_uploaded_at = timezone.now()
            self.audio_expires_at = self.audio_uploaded_at + datetime.timedelta(
                hours=24
            )

        super().save(*args, **kwargs)

    def is_audio_expired(self):
        from django.utils import timezone

        if not self.audio_expires_at:
            return False
        return timezone.now() >= self.audio_expires_at
