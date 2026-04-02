from django.db import models

from apps.documents.models import Document
from apps.encounters.models import Encounter
from apps.users.models import User


class CopilotRun(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("running", "Running"),
        ("waiting_review", "Waiting Review"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    run_id = models.CharField(max_length=64, unique=True)
    thread_id = models.CharField(max_length=255)
    doctor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="copilot_runs",
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="copilot_runs",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="created")
    intent = models.CharField(max_length=64, null=True, blank=True)
    requires_human_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["doctor", "encounter"]),
            models.Index(fields=["thread_id"]),
        ]

    def __str__(self) -> str:
        return f"CopilotRun {self.run_id} ({self.status})"


class CopilotPatch(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("applied", "Applied"),
        ("stale", "Stale"),
    ]

    patch_id = models.CharField(max_length=64, unique=True)
    run = models.ForeignKey(
        CopilotRun,
        on_delete=models.CASCADE,
        related_name="patches",
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="copilot_patches",
    )
    doctor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="copilot_patches",
    )
    target_document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="copilot_patches",
    )
    base_version = models.IntegerField(default=1)
    operation_type = models.CharField(max_length=64)
    anchor = models.JSONField(default=dict, blank=True)
    expected_hash = models.CharField(max_length=128, blank=True, null=True)
    before_preview = models.TextField(blank=True, null=True)
    after_preview = models.TextField(blank=True, null=True)
    document_preview_after = models.TextField(blank=True, null=True)
    content_preview = models.TextField()
    rationale = models.TextField(blank=True, null=True)
    source_context_document_ids = models.JSONField(default=list, blank=True)
    target_document_title = models.CharField(max_length=255, blank=True, null=True)
    target_selection_reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    review_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["run", "status"]),
            models.Index(fields=["doctor", "encounter"]),
            models.Index(fields=["target_document"]),
        ]

    def __str__(self) -> str:
        return f"CopilotPatch {self.patch_id} ({self.status})"
