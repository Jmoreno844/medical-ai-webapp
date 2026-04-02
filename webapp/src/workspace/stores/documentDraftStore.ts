import { create } from "zustand";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import { DocumentDraftState } from "@/workspace/types";

type DocumentDraftStoreState = {
  draftsByDocumentId: Record<string, DocumentDraftState | null>;
  getDraft: (documentId: string) => DocumentDraftState | null;
  setDraft: (draft: DocumentDraftState) => void;
  setDraftContent: (documentId: string, content: string) => void;
  resetDraftFromSnapshot: (documentId: string) => void;
  markDraftClean: (documentId: string) => void;
  markDraftDirty: (documentId: string) => void;
  clearDrafts: () => void;
};

export const useDocumentDraftStore = create<DocumentDraftStoreState>(
  (set, get) => ({
    draftsByDocumentId: {},
    getDraft: (documentId) => get().draftsByDocumentId[documentId] ?? null,
    setDraft: (draft) =>
      set((state) => ({
        draftsByDocumentId: {
          ...state.draftsByDocumentId,
          [draft.documentId]: draft,
        },
      })),
    setDraftContent: (documentId, content) =>
      set((state) => ({
        draftsByDocumentId: {
          ...state.draftsByDocumentId,
          [documentId]: {
            documentId,
            localUnsavedContent: content,
            isDirty: true,
            lastEditedAt: new Date().toISOString(),
          },
        },
      })),
    resetDraftFromSnapshot: (documentId) => {
      const snapshot = useDocumentSnapshotStore.getState().getSnapshot(documentId);
      if (!snapshot) {
        return;
      }

      set((state) => ({
        draftsByDocumentId: {
          ...state.draftsByDocumentId,
          [documentId]: {
            documentId,
            localUnsavedContent: snapshot.contentMarkdown,
            isDirty: false,
            lastEditedAt: state.draftsByDocumentId[documentId]?.lastEditedAt,
          },
        },
      }));
    },
    markDraftClean: (documentId) =>
      set((state) => {
        const existingDraft = state.draftsByDocumentId[documentId];
        if (!existingDraft) {
          return state;
        }

        return {
          draftsByDocumentId: {
            ...state.draftsByDocumentId,
            [documentId]: {
              ...existingDraft,
              isDirty: false,
            },
          },
        };
      }),
    markDraftDirty: (documentId) =>
      set((state) => {
        const existingDraft = state.draftsByDocumentId[documentId];
        if (!existingDraft) {
          return state;
        }

        return {
          draftsByDocumentId: {
            ...state.draftsByDocumentId,
            [documentId]: {
              ...existingDraft,
              isDirty: true,
              lastEditedAt: new Date().toISOString(),
            },
          },
        };
      }),
    clearDrafts: () => set({ draftsByDocumentId: {} }),
  })
);
