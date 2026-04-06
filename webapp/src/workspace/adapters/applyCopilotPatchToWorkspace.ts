import { createChildLogger } from "@/lib/logger";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";

const log = createChildLogger("applyCopilotPatch");

type ApplyCopilotPatchToWorkspaceParams = {
  documentId: string;
  content: string;
  baseVersion: number;
  appliedVersion?: number | null;
};

export function applyCopilotPatchToWorkspace({
  documentId,
  content,
  baseVersion,
  appliedVersion,
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
    appliedVersion ?? Math.max(existingSnapshot?.version ?? 1, baseVersion) + 1;

  log.debug("applying patch to workspace", {
    documentId,
    nextVersion,
    activeDocumentId,
    isDirty: existingDraft?.isDirty,
    editorMode: existingDerivedState?.editorMode,
    hasSnapshot: !!existingSnapshot,
    contentLength: content.length,
  });

  snapshotStore.setSnapshot(documentId, content, nextVersion);

  if (
    !existingDraft?.isDirty ||
    existingDerivedState?.editorMode === "patch_review" ||
    activeDocumentId === documentId
  ) {
    draftStore.resetDraftFromSnapshot(documentId);
    draftStore.markDraftClean(documentId);
    log.debug("draft reset from new snapshot", { documentId });
  } else {
    // Draft has unsaved local edits on a background document.
    // Snapshot is updated but the draft is kept to avoid discarding the doctor's work.
    // The editor will show the new content on next focus/reload.
    log.warn("patch applied to snapshot but draft is dirty — draft NOT reset", {
      documentId,
      activeDocumentId,
    });
  }

  derivedStore.clearPatchPreview(documentId);

  // Clear the entire patch set store so PatchInlineDiffView unmounts and the
  // Lexical editor re-renders with the new (markdown-parsed) content.
  log.debug("clearing all patches from state store");
  patchSetStore.clearAll();

  log.debug("triggering editor refresh");
  window.triggerEditorRefresh?.();
}
