import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { WorkspaceIndex } from "@/workspace/types";

export function buildWorkspaceIndex(): WorkspaceIndex {
  const workspaceState = useWorkspaceStore.getState();
  const draftState = useDocumentDraftStore.getState();
  const derivedState = useDocumentDerivedStore.getState();
  const snapshotState = useDocumentSnapshotStore.getState();
  const patchSetState = usePatchSetStore.getState();

  const documents = workspaceState.documentOrder
    .map((documentId) => workspaceState.documentsById[documentId])
    .filter(Boolean)
    .map((document) => {
      const draft = draftState.draftsByDocumentId[document.id];
      const derived = derivedState.derivedByDocumentId[document.id];
      const snapshot = snapshotState.snapshotsByDocumentId[document.id];
      
      const activePatchSet = patchSetState.activePatchSetId 
        ? patchSetState.patchSets[patchSetState.activePatchSetId]
        : null;
      const patches = activePatchSet?.patches.filter(p => p.documentId === document.id && p.status === "pending") ?? [];
      const contentForExcerpt =
        draft?.localUnsavedContent ??
        snapshot?.contentMarkdown ??
        document.contentMarkdown;

      return {
        documentId: document.id,
        type: document.type,
        title: document.title,
        status: document.status,
        source: document.source,
        aiReadable: document.aiReadable,
        aiWritable: document.aiWritable,
        version: snapshot?.version ?? document.version,
        updatedAt:
          draft?.lastEditedAt ??
          derived?.updatedAt ??
          snapshot?.savedAt ??
          document.updatedAt,
        isActive: workspaceState.activeDocumentId === document.id,
        isOpen: workspaceState.openDocumentIds.includes(document.id),
        hasDirtyDraft: Boolean(draft?.isDirty),
        hasStreamingState:
          Boolean(derived?.inProgress) && Boolean(derived?.streamingContent),
        hiddenFromAgent: workspaceState.hiddenFromAgentDocumentIds.includes(
          document.id
        ),
        pinnedForAgent: workspaceState.pinnedDocumentIds.includes(document.id),
        excerpt: contentForExcerpt.trim().slice(0, 160) || undefined,
        shortSummary: document.summaryShort,
        estimatedTokens: document.estimatedTokens,
        hasPendingPatches: patches.length > 0,
      };
    });

  const workspaceVersion = documents
    .map(
      (document) =>
        [
          document.documentId,
          document.version,
          document.updatedAt,
          document.hasDirtyDraft ? "dirty" : "clean",
          document.hasStreamingState ? "streaming" : "stable",
          document.hasPendingPatches ? "patch" : "no-patch",
        ].join(":")
    )
    .join("|");

  return {
    encounterId: workspaceState.loadedEncounterId ?? "",
    workspaceVersion,
    activeDocumentId: workspaceState.activeDocumentId,
    openDocumentIds: workspaceState.openDocumentIds,
    documents,
  };
}
