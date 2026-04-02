import { create } from "zustand";
import { buildWorkspaceIndex } from "@/workspace/builders/workspaceIndex";
import { AiSessionReadMode } from "@/workspace/types";

type AiSessionStoreState = {
  selectedDocumentIds: string[];
  workingSetDocumentIds: string[];
  lastWorkspaceVersionSeen: string | null;
  readMode: AiSessionReadMode;
  setSelectedDocumentIds: (documentIds: string[]) => void;
  setWorkingSetDocumentIds: (documentIds: string[]) => void;
  setLastWorkspaceVersionSeen: (version: string | null) => void;
  setReadMode: (readMode: AiSessionReadMode) => void;
  syncWorkingSetFromWorkspace: () => void;
  clearSession: () => void;
};

export const useAiSessionStore = create<AiSessionStoreState>((set) => ({
  selectedDocumentIds: [],
  workingSetDocumentIds: [],
  lastWorkspaceVersionSeen: null,
  readMode: "active_only",
  setSelectedDocumentIds: (documentIds) => set({ selectedDocumentIds: documentIds }),
  setWorkingSetDocumentIds: (documentIds) =>
    set({ workingSetDocumentIds: documentIds }),
  setLastWorkspaceVersionSeen: (version) =>
    set({ lastWorkspaceVersionSeen: version }),
  setReadMode: (readMode) => set({ readMode }),
  syncWorkingSetFromWorkspace: () => {
    const workspaceIndex = buildWorkspaceIndex();
    const workingSetDocumentIds = workspaceIndex.documents
      .filter(
        (document) =>
          document.isActive || document.isOpen || document.pinnedForAgent
      )
      .map((document) => document.documentId);

    set({
      workingSetDocumentIds,
      lastWorkspaceVersionSeen: workspaceIndex.workspaceVersion,
    });
  },
  clearSession: () =>
    set({
      selectedDocumentIds: [],
      workingSetDocumentIds: [],
      lastWorkspaceVersionSeen: null,
      readMode: "active_only",
    }),
}));
