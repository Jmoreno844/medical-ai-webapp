import { create } from "zustand";
import { DocumentoOut } from "@/types/documento";
import { logger } from "@/lib/logger";
import { adaptDocumentoToWorkspaceDocument } from "@/workspace/adapters/documentAdapter";
import { WorkspaceDocument } from "@/workspace/types";

type WorkspaceStoreState = {
  documentsById: Record<string, WorkspaceDocument>;
  documentOrder: string[];
  openDocumentIds: string[];
  activeDocumentId: string | null;
  pinnedDocumentIds: string[];
  hiddenFromAgentDocumentIds: string[];
  loading: boolean;
  error: string | null;
  loadedEncounterId: string | null;
  bootstrapEncounterDocuments: (
    encounterId: number | string,
    docs: DocumentoOut[],
  ) => void;
  setActiveDocument: (documentId: string | null) => void;
  addDocument: (doc: DocumentoOut, encounterId: number | string) => void;
  removeDocument: (documentId: string) => void;
  upsertDocument: (doc: DocumentoOut, encounterId: number | string) => void;
  setDocumentPinnedForAgent: (documentId: string, pinned: boolean) => void;
  setDocumentHiddenFromAgent: (documentId: string, hidden: boolean) => void;
  clearEncounterWorkspace: () => void;
  setWorkspaceLoading: (loading: boolean) => void;
  setWorkspaceError: (error: string | null) => void;
  // True while the copilot agent is actively streaming a run.
  // Used by the editor to show a light lock overlay so the doctor
  // knows AI is working and edits may be overwritten.
  isCopilotRunning: boolean;
  setCopilotRunning: (running: boolean) => void;
};

function sortDocuments(docs: DocumentoOut[]): DocumentoOut[] {
  return [...docs].sort((a, b) => {
    const dateA = new Date(a.created_on).getTime();
    const dateB = new Date(b.created_on).getTime();

    if (dateA !== dateB) {
      return dateA - dateB;
    }

    return a.id - b.id;
  });
}

function buildWorkspaceMap(
  docs: DocumentoOut[],
  encounterId: number | string,
): Record<string, WorkspaceDocument> {
  return sortDocuments(docs).reduce<Record<string, WorkspaceDocument>>(
    (acc, doc) => {
      const workspaceDoc = adaptDocumentoToWorkspaceDocument(doc, encounterId);
      acc[workspaceDoc.id] = workspaceDoc;
      return acc;
    },
    {},
  );
}

function getDocumentOrder(docs: DocumentoOut[]): string[] {
  return sortDocuments(docs).map((doc) => String(doc.id));
}

export const useWorkspaceStore = create<WorkspaceStoreState>((set) => ({
  documentsById: {},
  documentOrder: [],
  openDocumentIds: [],
  activeDocumentId: null,
  pinnedDocumentIds: [],
  hiddenFromAgentDocumentIds: [],
  loading: false,
  error: null,
  loadedEncounterId: null,

  bootstrapEncounterDocuments: (encounterId, docs) => {
    const orderedIds = getDocumentOrder(docs);
    const encounterKey = String(encounterId);

    set((state) => {
      const previousActiveId =
        state.loadedEncounterId === encounterKey
          ? state.activeDocumentId
          : null;
      const nextActiveId =
        previousActiveId && orderedIds.includes(previousActiveId)
          ? previousActiveId
          : (orderedIds[0] ?? null);

      return {
        documentsById: buildWorkspaceMap(docs, encounterId),
        documentOrder: orderedIds,
        openDocumentIds: orderedIds,
        activeDocumentId: nextActiveId,
        loadedEncounterId: encounterKey,
      };
    });
  },

  setActiveDocument: (documentId) => {
    set((state) => {
      if (documentId === null || state.activeDocumentId === documentId) {
        return state;
      }

      if (!(documentId in state.documentsById)) {
        logger.warn(
          "[WORKSPACE] Tried to activate unknown document %s",
          documentId,
        );
        return state;
      }

      return { activeDocumentId: documentId };
    });
  },

  addDocument: (doc, encounterId) => {
    set((state) => {
      const workspaceDoc = adaptDocumentoToWorkspaceDocument(doc, encounterId);
      const nextDocumentsById = {
        ...state.documentsById,
        [workspaceDoc.id]: workspaceDoc,
      };
      const nextOrder = getDocumentOrder(
        Object.values(nextDocumentsById).map((item) => ({
          id: Number(item.id),
          encounter_id: Number(item.encounterId),
          kind: String(item.metadata.kind ?? item.type),
          doctor_template_id:
            typeof item.metadata.doctor_template_id === "number" ||
            item.metadata.doctor_template_id === null
              ? (item.metadata.doctor_template_id as number | null)
              : null,
          content: item.contentMarkdown,
          created_on: String(item.metadata.created_on ?? item.createdAt),
          doctor_id: Number(item.metadata.doctor_id ?? 0),
        })),
      );

      return {
        documentsById: nextDocumentsById,
        documentOrder: nextOrder,
        openDocumentIds: nextOrder,
      };
    });
  },

  removeDocument: (documentId) => {
    set((state) => {
      if (!(documentId in state.documentsById)) {
        return state;
      }

      const nextDocumentsById = { ...state.documentsById };
      delete nextDocumentsById[documentId];

      const nextOrder = state.documentOrder.filter((id) => id !== documentId);
      let nextActiveId = state.activeDocumentId;

      if (state.activeDocumentId === documentId) {
        const removedIndex = state.documentOrder.indexOf(documentId);
        nextActiveId =
          nextOrder[removedIndex] ?? nextOrder[removedIndex - 1] ?? null;
      }

      return {
        documentsById: nextDocumentsById,
        documentOrder: nextOrder,
        openDocumentIds: nextOrder,
        activeDocumentId: nextActiveId,
      };
    });
  },

  upsertDocument: (doc, encounterId) => {
    set((state) => {
      const workspaceDoc = adaptDocumentoToWorkspaceDocument(doc, encounterId);
      const nextDocumentsById = {
        ...state.documentsById,
        [workspaceDoc.id]: workspaceDoc,
      };
      const nextOrder = getDocumentOrder(
        Object.values(nextDocumentsById).map((item) => ({
          id: Number(item.id),
          encounter_id: Number(item.encounterId),
          kind: String(item.metadata.kind ?? item.type),
          doctor_template_id:
            typeof item.metadata.doctor_template_id === "number" ||
            item.metadata.doctor_template_id === null
              ? (item.metadata.doctor_template_id as number | null)
              : null,
          content: item.contentMarkdown,
          created_on: String(item.metadata.created_on ?? item.createdAt),
          doctor_id: Number(item.metadata.doctor_id ?? 0),
        })),
      );

      return {
        documentsById: nextDocumentsById,
        documentOrder: nextOrder,
        openDocumentIds: nextOrder,
      };
    });
  },

  setDocumentPinnedForAgent: (documentId, pinned) =>
    set((state) => ({
      pinnedDocumentIds: pinned
        ? [...new Set([...state.pinnedDocumentIds, documentId])]
        : state.pinnedDocumentIds.filter((id) => id !== documentId),
    })),

  setDocumentHiddenFromAgent: (documentId, hidden) =>
    set((state) => ({
      hiddenFromAgentDocumentIds: hidden
        ? [...new Set([...state.hiddenFromAgentDocumentIds, documentId])]
        : state.hiddenFromAgentDocumentIds.filter((id) => id !== documentId),
    })),

  clearEncounterWorkspace: () =>
    set({
      documentsById: {},
      documentOrder: [],
      openDocumentIds: [],
      activeDocumentId: null,
      pinnedDocumentIds: [],
      hiddenFromAgentDocumentIds: [],
      loading: false,
      error: null,
      loadedEncounterId: null,
    }),

  setWorkspaceLoading: (loading) => set({ loading }),
  setWorkspaceError: (error) => set({ error }),
  isCopilotRunning: false,
  setCopilotRunning: (running) => set({ isCopilotRunning: running }),
}));
