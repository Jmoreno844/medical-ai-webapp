from django.db import models
from apps.users.models import User


class Paciente(models.Model):
    nombre = models.CharField(max_length=255)
    resumen = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class PacienteMedico(models.Model):
    id_medico = models.ForeignKey(User, on_delete=models.CASCADE)
    id_paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("id_medico", "id_paciente")
        indexes = [
            models.Index(fields=["id_medico"]),
            models.Index(fields=["id_paciente"]),
        ]

    def __str__(self):
        return f"{self.id_paciente.nombre} - {self.id_medico.get_full_name()}"
