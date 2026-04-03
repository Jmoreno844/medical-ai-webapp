from __future__ import annotations

from dataclasses import dataclass

from apps.copilot.models import CopilotPatch
from apps.copilot.services.patch_sets import (
    CopilotPatchSetConflictError,
    CopilotPatchSetError,
    apply_accepted_patch_set,
    ensure_patch_set_for_legacy_patch,
)


class CopilotPatchApplyError(CopilotPatchSetError):
    pass


class CopilotPatchConflictError(CopilotPatchSetConflictError, CopilotPatchApplyError):
    pass


@dataclass(frozen=True)
class CopilotPatchApplyResult:
    patch_id: str
    document_id: str
    content: str
    applied_version: int
    stale_patch_ids: list[str]


def apply_copilot_patch(
    *,
    patch: CopilotPatch,
    document_version: int | None = None,
    review_comment: str | None = None,
) -> CopilotPatchApplyResult:
    """Legacy single-patch wrapper around patch-set apply.

    The current debug UI still speaks in terms of one patch per review. Internally we
    normalize that flow into a one-document patch set so Django remains the only
    authority that applies canonical document writes.
    """

    patch_set = ensure_patch_set_for_legacy_patch(patch)
    if patch.status != "accepted":
        patch.status = "accepted"
        patch.review_comment = review_comment
        patch.save(update_fields=["status", "review_comment", "updated_at"])

    apply_result = apply_accepted_patch_set(
        patch_set=patch_set,
        document_version=document_version,
        review_comment=review_comment,
    )
    stale_patch_ids = [
        stale_patch_id
        for stale_patch_id in apply_result.stale_patch_ids
        if stale_patch_id != patch.patch_id
    ]
    return CopilotPatchApplyResult(
        patch_id=patch.patch_id,
        document_id=apply_result.document_id,
        content=apply_result.content,
        applied_version=apply_result.applied_version,
        stale_patch_ids=stale_patch_ids,
    )
