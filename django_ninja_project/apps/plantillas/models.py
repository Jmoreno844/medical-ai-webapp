from django.db import models
from apps.users.models import User


class TipoDocumento(models.TextChoices):
    """Enum for document types used in templates."""

    NOTA = "nota", "Nota"
    DOCUMENTO = "documento", "Documento"
    OTROS = "otros", "Otros"


class PlantillaBase(models.Model):
    """
    Base template model that can be used as a starting point for doctor-specific templates.
    These could be system-provided templates or shared templates.
    """

    nombre = models.CharField(max_length=255)
    tipo_documento = models.CharField(
        max_length=50, choices=TipoDocumento.choices, default=TipoDocumento.OTROS
    )
    contenido = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tipo_documento"]),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_documento_display()})"


class PlantillaDoctor(models.Model):
    """
    Doctor-specific templates that can either be derived from a base template
    or created from scratch by the doctor.
    """

    nombre = models.CharField(max_length=255)
    tipo_documento = models.CharField(
        max_length=50, choices=TipoDocumento.choices, default=TipoDocumento.OTROS
    )
    contenido_base = models.BooleanField(default=False)
    id_plantilla_base = models.ForeignKey(
        PlantillaBase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plantillas_derivadas",
    )
    contenido = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    id_medico = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="plantillas_doctor"
    )

    class Meta:
        indexes = [
            models.Index(fields=["id_medico"]),
            models.Index(fields=["tipo_documento"]),
            models.Index(fields=["id_plantilla_base"]),
        ]

    def __str__(self):
        base_info = (
            f" (basado en: {self.id_plantilla_base.nombre})"
            if self.id_plantilla_base
            else ""
        )
        return f"{self.nombre} ({self.get_tipo_documento_display()}){base_info}"

    def get_contenido_efectivo(self):
        """
        Returns the effective content for this template,
        using base template content if this is marked as using base content
        """
        if self.contenido_base and self.id_plantilla_base:
            return self.id_plantilla_base.contenido
        return self.contenido
