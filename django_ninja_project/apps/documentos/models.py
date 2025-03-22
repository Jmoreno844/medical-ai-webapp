from django.db import models
from apps.encuentro.models import Encuentro
from apps.users.models import User
from apps.plantillas.models import PlantillaDoctor


class Documento(models.Model):
    TIPO_CHOICES = [
        ("contexto", "Contexto"),
        ("transcripcion", "Transcripción"),
        ("plantilla", "Plantilla"),
        ("nota", "Nota"),
    ]

    id_encuentro = models.ForeignKey(
        Encuentro, on_delete=models.CASCADE, related_name="documentos"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    id_plantilla_doctor = models.ForeignKey(
        PlantillaDoctor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos",
    )
    contenido = models.TextField()
    fecha_creacion = models.DateField(auto_now_add=True)
    id_medico = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="documentos"
    )

    def __str__(self):
        return f"{self.tipo} - Encuentro {self.id_encuentro.id} - {self.fecha_creacion}"
