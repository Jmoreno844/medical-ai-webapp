import { WorkspaceDocument } from "@/workspace/types";
import { buildWorkspaceIndex } from "@/workspace/builders/workspaceIndex";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";

type WorkspaceSelectorState = ReturnType<typeof useWorkspaceStore.getState>;

export const selectWorkspaceDocuments = (
  state: WorkspaceSelectorState
): WorkspaceDocument[] =>
  state.documentOrder
    .map((documentId) => state.documentsById[documentId])
    .filter((document): document is WorkspaceDocument => Boolean(document));

export const selectActiveWorkspaceDocument = (
  state: WorkspaceSelectorState
): WorkspaceDocument | null => {
  if (!state.activeDocumentId) {
    return null;
  }

  return state.documentsById[state.activeDocumentId] ?? null;
};

export const selectActiveWorkspaceDocumentId = (
  state: WorkspaceSelectorState
): string | null => state.activeDocumentId;

export const selectOpenWorkspaceDocumentIds = (
  state: WorkspaceSelectorState
): string[] => state.openDocumentIds;

export const selectWorkspaceIndex = () => buildWorkspaceIndex();

export const selectActiveReadableDocuments = () =>
  buildWorkspaceIndex().documents.filter(
    (document) => document.aiReadable && document.isActive
  );

export const selectDirtyDocuments = () =>
  buildWorkspaceIndex().documents.filter((document) => document.hasDirtyDraft);

export const selectDocumentsVisibleToAgent = () =>
  buildWorkspaceIndex().documents.filter(
    (document) => document.aiReadable && !document.hiddenFromAgent
  );
