import { create } from "zustand";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import { DocumentDraftState, DocumentJsonContent } from "@/workspace/types";

const DOCUMENT_DRAFT_STORAGE_KEY = "medical-web-app.document-drafts.v1";
const DOCUMENT_DRAFT_PERSIST_DEBOUNCE_MS = 400;

type PersistedDocumentDraft = Pick<
  DocumentDraftState,
  | "documentId"
  | "localUnsavedContent"
  | "localUnsavedContentJson"
  | "isDirty"
  | "lastEditedAt"
  | "userEditedSinceLastCopilotTurn"
>;

function isBrowser(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.localStorage !== "undefined"
  );
}

function sanitizeDraft(
  value: unknown,
  fallbackDocumentId?: string,
): DocumentDraftState | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }

  const candidate = value as Record<string, unknown>;
  const documentId =
    typeof candidate.documentId === "string"
      ? candidate.documentId
      : fallbackDocumentId;
  if (!documentId) {
    return null;
  }

  return {
    documentId,
    localUnsavedContent:
      typeof candidate.localUnsavedContent === "string" ||
      candidate.localUnsavedContent === null
        ? candidate.localUnsavedContent
        : "",
    localUnsavedContentJson:
      typeof candidate.localUnsavedContentJson === "object" ||
      candidate.localUnsavedContentJson === null
        ? (candidate.localUnsavedContentJson as DocumentJsonContent)
        : null,
    isDirty: Boolean(candidate.isDirty),
    lastEditedAt:
      typeof candidate.lastEditedAt === "string"
        ? candidate.lastEditedAt
        : undefined,
    userEditedSinceLastCopilotTurn:
      typeof candidate.userEditedSinceLastCopilotTurn === "boolean"
        ? candidate.userEditedSinceLastCopilotTurn
        : undefined,
  };
}

function loadPersistedDrafts(): Record<string, DocumentDraftState | null> {
  if (!isBrowser()) {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(DOCUMENT_DRAFT_STORAGE_KEY);
    if (!raw) {
      return {};
    }

    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return {};
    }

    return Object.entries(parsed as Record<string, unknown>).reduce<
      Record<string, DocumentDraftState | null>
    >((acc, [documentId, draft]) => {
      const sanitized = sanitizeDraft(draft, documentId);
      if (sanitized) {
        acc[documentId] = sanitized;
      }
      return acc;
    }, {});
  } catch {
    return {};
  }
}

let persistTimer: number | null = null;

function persistDrafts(
  draftsByDocumentId: Record<string, DocumentDraftState | null>,
): void {
  if (!isBrowser()) {
    return;
  }

  const persistedDrafts = Object.entries(draftsByDocumentId).reduce<
    Record<string, PersistedDocumentDraft>
  >((acc, [documentId, draft]) => {
    if (!draft) {
      return acc;
    }
    acc[documentId] = {
      documentId: draft.documentId,
      localUnsavedContent: draft.localUnsavedContent,
      localUnsavedContentJson:
        typeof draft.localUnsavedContentJson === "undefined"
          ? null
          : (draft.localUnsavedContentJson ?? null),
      isDirty: draft.isDirty,
      lastEditedAt: draft.lastEditedAt,
      userEditedSinceLastCopilotTurn: draft.userEditedSinceLastCopilotTurn,
    };
    return acc;
  }, {});

  try {
    if (Object.keys(persistedDrafts).length === 0) {
      window.localStorage.removeItem(DOCUMENT_DRAFT_STORAGE_KEY);
      return;
    }

    window.localStorage.setItem(
      DOCUMENT_DRAFT_STORAGE_KEY,
      JSON.stringify(persistedDrafts),
    );
  } catch {
    // Best-effort only: if storage is unavailable/full, keep the in-memory draft.
  }
}

function schedulePersistDrafts(
  draftsByDocumentId: Record<string, DocumentDraftState | null>,
): void {
  if (!isBrowser()) {
    return;
  }

  if (persistTimer !== null) {
    window.clearTimeout(persistTimer);
  }

  persistTimer = window.setTimeout(() => {
    persistDrafts(draftsByDocumentId);
    persistTimer = null;
  }, DOCUMENT_DRAFT_PERSIST_DEBOUNCE_MS);
}

type DocumentDraftStoreState = {
  draftsByDocumentId: Record<string, DocumentDraftState | null>;
  getDraft: (documentId: string) => DocumentDraftState | null;
  setDraft: (draft: DocumentDraftState) => void;
  setDraftContent: (
    documentId: string,
    content: string,
    contentJson?: DocumentJsonContent,
  ) => void;
  resetDraftFromSnapshot: (documentId: string) => void;
  markDraftClean: (documentId: string) => void;
  markDraftDirty: (documentId: string) => void;
  clearDrafts: () => void;
  // Resets userEditedSinceLastCopilotTurn for the given document IDs after a
  // successful copilot submission so the notices are not re-sent next turn.
  markCopilotTurnConsumed: (documentIds: string[]) => void;
};

export const useDocumentDraftStore = create<DocumentDraftStoreState>(
  (set, get) => ({
    draftsByDocumentId: loadPersistedDrafts(),
    getDraft: (documentId) => get().draftsByDocumentId[documentId] ?? null,
    setDraft: (draft) =>
      set((state) => {
        const draftsByDocumentId = {
          ...state.draftsByDocumentId,
          [draft.documentId]: draft,
        };
        schedulePersistDrafts(draftsByDocumentId);
        return { draftsByDocumentId };
      }),
    setDraftContent: (documentId, content, contentJson) =>
      set((state) => {
        const existingDraft = state.draftsByDocumentId[documentId];
        const draftsByDocumentId = {
          ...state.draftsByDocumentId,
          [documentId]: {
            documentId,
            localUnsavedContent: content,
            localUnsavedContentJson:
              typeof contentJson === "undefined"
                ? (existingDraft?.localUnsavedContentJson ?? null)
                : contentJson,
            isDirty: true,
            lastEditedAt: new Date().toISOString(),
            // Preserve the notice flag so it stays true even after autosave
            // clears isDirty. It is only reset by markCopilotTurnConsumed.
            userEditedSinceLastCopilotTurn:
              existingDraft?.userEditedSinceLastCopilotTurn ?? true,
          },
        };
        schedulePersistDrafts(draftsByDocumentId);
        return { draftsByDocumentId };
      }),
    resetDraftFromSnapshot: (documentId) => {
      const snapshot = useDocumentSnapshotStore
        .getState()
        .getSnapshot(documentId);
      if (!snapshot) {
        return;
      }

      set((state) => {
        const existingDraft = state.draftsByDocumentId[documentId];
        const draftsByDocumentId = {
          ...state.draftsByDocumentId,
          [documentId]: {
            documentId,
            localUnsavedContent: snapshot.contentMarkdown,
            localUnsavedContentJson: snapshot.contentJson ?? null,
            isDirty: false,
            lastEditedAt: existingDraft?.lastEditedAt,
            userEditedSinceLastCopilotTurn:
              existingDraft?.userEditedSinceLastCopilotTurn,
          },
        };
        schedulePersistDrafts(draftsByDocumentId);
        return { draftsByDocumentId };
      });
    },
    markDraftClean: (documentId) =>
      set((state) => {
        const existingDraft = state.draftsByDocumentId[documentId];
        if (!existingDraft) {
          return state;
        }

        const draftsByDocumentId = {
          ...state.draftsByDocumentId,
          [documentId]: {
            ...existingDraft,
            isDirty: false,
          },
        };
        schedulePersistDrafts(draftsByDocumentId);
        return { draftsByDocumentId };
      }),
    markDraftDirty: (documentId) =>
      set((state) => {
        const existingDraft = state.draftsByDocumentId[documentId];
        if (!existingDraft) {
          return state;
        }

        const draftsByDocumentId = {
          ...state.draftsByDocumentId,
          [documentId]: {
            ...existingDraft,
            isDirty: true,
            lastEditedAt: new Date().toISOString(),
          },
        };
        schedulePersistDrafts(draftsByDocumentId);
        return { draftsByDocumentId };
      }),
    clearDrafts: () => {
      if (persistTimer !== null && isBrowser()) {
        window.clearTimeout(persistTimer);
        persistTimer = null;
      }
      persistDrafts({});
      set({ draftsByDocumentId: {} });
    },
    markCopilotTurnConsumed: (documentIds) =>
      set((state) => {
        const updated: Record<string, DocumentDraftState | null> = {
          ...state.draftsByDocumentId,
        };
        for (const id of documentIds) {
          const draft = updated[id];
          if (draft) {
            updated[id] = { ...draft, userEditedSinceLastCopilotTurn: false };
          }
        }
        schedulePersistDrafts(updated);
        return { draftsByDocumentId: updated };
      }),
  })
);
