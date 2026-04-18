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
            models.Index(
                fields=["doctor", "encounter"],
                name="copilot_cop_doctor__553b6b_idx",
            ),
            models.Index(
                fields=["thread_id"],
                name="copilot_cop_thread__60ab29_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"CopilotRun {self.run_id} ({self.status})"


class CopilotPatchSet(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("partially_accepted", "Partially Accepted"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("stale", "Stale"),
        ("applied", "Applied"),
    ]

    patch_set_id = models.CharField(max_length=64, unique=True)
    run = models.ForeignKey(
        CopilotRun,
        on_delete=models.CASCADE,
        related_name="patch_sets",
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="copilot_patch_sets",
    )
    doctor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="copilot_patch_sets",
    )
    target_document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="copilot_patch_sets",
    )
    base_version = models.IntegerField(default=1)
    base_hash = models.CharField(max_length=128)
    rationale = models.TextField(blank=True, null=True)
    source_context_document_ids = models.JSONField(default=list, blank=True)
    target_document_title = models.CharField(max_length=255, blank=True, null=True)
    target_selection_reason = models.TextField(blank=True, null=True)
    document_preview_after = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    # Campos del plan clínico estructurado emitidos por el copiloto vía set_edit_plan.
    # edit_scope: 'local', 'propagation', 'reinterpretation'
    # clinical_impact_level: 'cosmetic', 'factual', 'clinical'
    # affected_sections: lista de secciones semánticas que el drafter tocó.
    edit_scope = models.CharField(max_length=32, blank=True, null=True)
    clinical_impact_level = models.CharField(max_length=32, blank=True, null=True)
    affected_sections = models.JSONField(default=list, blank=True)
    review_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["run", "status"],
                name="copilot_pset_run_status_idx",
            ),
            models.Index(
                fields=["doctor", "encounter"],
                name="copilot_pset_doctor_enc_idx",
            ),
            models.Index(
                fields=["target_document"],
                name="copilot_pset_target_doc_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"CopilotPatchSet {self.patch_set_id} ({self.status})"


class CopilotPatch(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("conflicted", "Conflicted"),
        ("applied", "Applied"),
        ("stale", "Stale"),
    ]

    patch_id = models.CharField(max_length=64, unique=True)
    patch_set = models.ForeignKey(
        CopilotPatchSet,
        on_delete=models.CASCADE,
        related_name="patches",
        null=True,
        blank=True,
    )
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
    order_index = models.IntegerField(default=0)
    patch_type = models.CharField(max_length=64, default="rewrite_document")
    operation_type = models.CharField(max_length=64)
    anchor = models.JSONField(default=dict, blank=True)
    expected_hash = models.CharField(max_length=128, blank=True, null=True)
    replacement_text = models.TextField(blank=True, null=True)
    inserted_text = models.TextField(blank=True, null=True)
    old_text = models.TextField(blank=True, null=True)
    new_text = models.TextField(blank=True, null=True)
    resolved_start = models.IntegerField(blank=True, null=True)
    resolved_end = models.IntegerField(blank=True, null=True)
    confidence = models.FloatField(blank=True, null=True)
    conflict_reason = models.TextField(blank=True, null=True)
    document_preview_after = models.TextField(blank=True, null=True)
    content_preview = models.TextField()
    rationale = models.TextField(blank=True, null=True)
    source_context_document_ids = models.JSONField(default=list, blank=True)
    target_document_title = models.CharField(max_length=255, blank=True, null=True)
    target_selection_reason = models.TextField(blank=True, null=True)
    # Sección semántica de la nota clínica a la que pertenece este patch.
    # Deriva del campo 'section' del DraftedPatch emitido por el drafter.
    section = models.CharField(max_length=128, blank=True, null=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    review_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["patch_set", "status"],
                name="copilot_patch_pset_status_idx",
            ),
            models.Index(
                fields=["run", "status"],
                name="copilot_cop_run_id_468f25_idx",
            ),
            models.Index(
                fields=["doctor", "encounter"],
                name="copilot_cop_doctor__6f0cd0_idx",
            ),
            models.Index(
                fields=["target_document"],
                name="copilot_cop_target__1321e5_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"CopilotPatch {self.patch_id} ({self.status})"
