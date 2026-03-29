from django.db import models
from apps.users.models import User


class TemplateDocumentKind(models.TextChoices):
    NOTE = "note", "Nota"
    DOCUMENT = "document", "Documento"
    OTHER = "other", "Otros"


class BaseTemplate(models.Model):
    name = models.CharField(max_length=255)
    document_kind = models.CharField(
        max_length=50,
        choices=TemplateDocumentKind.choices,
        default=TemplateDocumentKind.OTHER,
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["document_kind"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_document_kind_display()})"


class DoctorTemplate(models.Model):
    name = models.CharField(max_length=255)
    document_kind = models.CharField(
        max_length=50,
        choices=TemplateDocumentKind.choices,
        default=TemplateDocumentKind.OTHER,
    )
    uses_base_content = models.BooleanField(default=False)
    base_template = models.ForeignKey(
        BaseTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_templates",
    )
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    doctor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="doctor_templates"
    )

    class Meta:
        indexes = [
            models.Index(fields=["doctor"]),
            models.Index(fields=["document_kind"]),
            models.Index(fields=["base_template"]),
        ]

    def __str__(self):
        base_info = (
            f" (basado en: {self.base_template.name})" if self.base_template else ""
        )
        return f"{self.name} ({self.get_document_kind_display()}){base_info}"

    def get_effective_content(self):
        if self.uses_base_content and self.base_template:
            return self.base_template.content
        return self.content


class TemplateUsage(models.Model):
    doctor_template = models.ForeignKey(
        DoctorTemplate, on_delete=models.CASCADE, related_name="usage_records"
    )
    use_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    doctor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="template_usages"
    )

    class Meta:
        indexes = [
            models.Index(fields=["doctor_template"]),
            models.Index(fields=["doctor"]),
        ]
        unique_together = ["doctor_template", "doctor"]

    def __str__(self):
        return f"Usage of {self.doctor_template.name} by {self.doctor}"
