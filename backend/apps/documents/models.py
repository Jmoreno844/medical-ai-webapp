from django.db import models
from apps.encounters.models import Encounter
from apps.users.models import User
from apps.templates.models import DoctorTemplate
from apps.documents.services.rich_document_content import set_document_content_fields


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
    # Canonical editor payload for the clinical note. Markdown-only paths still
    # exist for copilot/apply compatibility, but backend write paths now
    # regenerate this field instead of silently nulling it out.
    content_json = models.JSONField(null=True, blank=True)
    content_markdown = models.TextField(default="")
    created_on = models.DateField(auto_now_add=True)
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")

    @property
    def content(self) -> str:
        """Legacy compatibility alias for markdown content."""
        return self.content_markdown or ""

    @content.setter
    def content(self, value: str) -> None:
        # Legacy markdown-only writes still need to keep the editor payload in sync.
        set_document_content_fields(
            self,
            content_markdown=value,
            preferred_source="markdown",
        )

    def __str__(self):
        return f"{self.kind} - Encounter {self.encounter_id} - {self.created_on}"
