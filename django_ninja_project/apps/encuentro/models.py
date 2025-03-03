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
    fecha = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["id_medico"]),
            models.Index(fields=["id_paciente"]),
        ]

    def __str__(self):
        return f"Encuentro {self.id} - {self.fecha}"
