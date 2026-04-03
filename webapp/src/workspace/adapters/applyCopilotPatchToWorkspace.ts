import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";

type ApplyCopilotPatchToWorkspaceParams = {
  documentId: string;
  content: string;
  baseVersion: number;
  appliedVersion?: number | null;
  appliedPatchId?: string | null;
};

export function applyCopilotPatchToWorkspace({
  documentId,
  content,
  baseVersion,
  appliedVersion,
  appliedPatchId,
}: ApplyCopilotPatchToWorkspaceParams) {
  const workspaceState = useWorkspaceStore.getState();
  const snapshotStore = useDocumentSnapshotStore.getState();
  const draftStore = useDocumentDraftStore.getState();
  const derivedStore = useDocumentDerivedStore.getState();
  const patchSetStore = usePatchSetStore.getState();

  const activeDocumentId = workspaceState.activeDocumentId
    ? String(workspaceState.activeDocumentId)
    : null;
  const existingSnapshot = snapshotStore.getSnapshot(documentId);
  const existingDraft = draftStore.getDraft(documentId);
  const existingDerivedState = derivedStore.getDerivedState(documentId);
  const nextVersion =
    appliedVersion ??
    Math.max(existingSnapshot?.version ?? 1, baseVersion) + 1;

  snapshotStore.setSnapshot(documentId, content, nextVersion);

  if (
    !existingDraft?.isDirty ||
    existingDerivedState?.editorMode === "patch_review" ||
    activeDocumentId === documentId
  ) {
    draftStore.resetDraftFromSnapshot(documentId);
    draftStore.markDraftClean(documentId);
  }

  derivedStore.clearPatchPreview(documentId);

  if (appliedPatchId && patchSetStore.selectedPatchId === appliedPatchId) {
    if (patchSetStore.activePatchSetId) {
       patchSetStore.updatePatchStatus(patchSetStore.activePatchSetId, appliedPatchId, "applied");
    }
    patchSetStore.setSelectedPatch(null);
  }

  window.triggerEditorRefresh?.();
}
