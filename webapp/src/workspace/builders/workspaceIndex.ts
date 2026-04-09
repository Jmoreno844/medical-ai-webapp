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
      const patches =
        activePatchSet?.patches.filter(
          (p) => p.documentId === document.id && p.status === "pending",
        ) ?? [];
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
        hasUserEdits: Boolean(draft?.userEditedSinceLastCopilotTurn),
        hasStreamingState:
          Boolean(derived?.inProgress) && Boolean(derived?.streamingContent),
        hiddenFromAgent: workspaceState.hiddenFromAgentDocumentIds.includes(
          document.id,
        ),
        pinnedForAgent: workspaceState.pinnedDocumentIds.includes(document.id),
        excerpt: contentForExcerpt.trim().slice(0, 160) || undefined,
        shortSummary: document.summaryShort,
        estimatedTokens: document.estimatedTokens,
        hasPendingPatches: patches.length > 0,
        // Pre-load full content for open, writable documents so the agent can
        // propose patches on turn 1 without a read_document round-trip.
        // Excluded when:
        // - the draft has unsaved changes that differ from the snapshot
        //   (base_version in any patch would be wrong), or
        // - the document is hidden or currently streaming.
        //
        // Note: isDirty can be true even if the draft content equals the
        // snapshot because Lexical fires onChange after DocumentContentPlugin
        // applies refreshed content. We compare the actual content strings so
        // that a transient isDirty=true after a patch apply does not
        // incorrectly exclude the pre-seed.
        contentMarkdown: (() => {
          if (!document.aiWritable) return undefined;
          if (workspaceState.hiddenFromAgentDocumentIds.includes(document.id))
            return undefined;
          if (derived?.inProgress && derived?.streamingContent) return undefined;
          const canonical =
            snapshot?.contentMarkdown ?? document.contentMarkdown ?? "";
          if (draft?.isDirty && draft.localUnsavedContent != null) {
            // Normalize with the same rules as saveContent in ContentContext so that
            // Lexical re-fires (onChange after DocumentContentPlugin refresh) that
            // produce slightly different whitespace do not incorrectly mark the
            // content as "different" and exclude the pre-seed.
            const normalize = (s: string) =>
              s
                .replace(/\r\n/g, "\n")
                .replace(/\r/g, "\n")
                .replace(/\n\n+/g, "\n\n")
                .replace(/[ \t]+/g, " ")
                .trim();
            if (normalize(draft.localUnsavedContent ?? "") !== normalize(canonical)) {
              // Real unsaved changes — exclude to avoid base_version mismatch.
              return undefined;
            }
          }
          return canonical || undefined;
        })(),
      };
    });

  const workspaceVersion = documents
    .map((document) =>
      [
        document.documentId,
        document.version,
        document.updatedAt,
        document.hasDirtyDraft ? "dirty" : "clean",
        document.hasStreamingState ? "streaming" : "stable",
        document.hasPendingPatches ? "patch" : "no-patch",
      ].join(":"),
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
