from django.db import models
from apps.users.models import User
from apps.pacientes.models import Paciente


class Encuentro(models.Model):
    id_medico = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="encuentros"
    )
    paciente_conectado = models.BooleanField(default=False)
    id_paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name="encuentros",
        null=True,
        blank=True,
    )
    nombre_encuentro = models.CharField(max_length=255, null=True, blank=True)
    fecha = models.DateTimeField()  # Changed from DateField to DateTimeField
    created_at = models.DateTimeField(auto_now_add=True)

    # New fields for audio handling
    audio_file_name = models.CharField(max_length=255, null=True, blank=True)
    audio_uploaded_at = models.DateTimeField(null=True, blank=True)
    audio_expires_at = models.DateTimeField(null=True, blank=True)
    audio_duration_seconds = models.IntegerField(null=True, blank=True)
    has_been_transcribed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["id_medico"]),
            models.Index(fields=["id_paciente"]),
        ]

    def __str__(self):
        return f"Encuentro {self.id} - {self.fecha}"

    def save(self, *args, **kwargs):
        # Set audio expiration time when uploading a new audio file
        if self.audio_file_name and not self.audio_uploaded_at:
            from django.utils import timezone
            import datetime

            self.audio_uploaded_at = timezone.now()
            self.audio_expires_at = self.audio_uploaded_at + datetime.timedelta(
                hours=24
            )

        super().save(*args, **kwargs)

    def is_audio_expired(self):
        """Check if the audio file has expired"""
        from django.utils import timezone

        if not self.audio_expires_at:
            return False
        return timezone.now() >= self.audio_expires_at
