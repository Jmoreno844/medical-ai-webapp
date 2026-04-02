import { create } from "zustand";
import { DocumentPatch } from "@/workspace/types";

type PatchStoreState = {
  patchesByDocumentId: Record<string, DocumentPatch[]>;
  pendingPatchIds: string[];
  selectedPatchId: string | null;
  previewContentByDocumentId: Record<string, string | null>;
  stalePatchIds: string[];
  patchSourceById: Record<string, DocumentPatch["createdBy"]>;
  setPatch: (patch: DocumentPatch) => void;
  setPatchesForDocument: (
    documentId: string,
    patches: DocumentPatch[]
  ) => void;
  selectPatch: (patchId: string | null) => void;
  setPreviewContent: (documentId: string, content: string | null) => void;
  markPatchStale: (patchId: string) => void;
  clearDocumentPatches: (documentId: string) => void;
  clearPatches: () => void;
};

export const usePatchStore = create<PatchStoreState>((set) => ({
  patchesByDocumentId: {},
  pendingPatchIds: [],
  selectedPatchId: null,
  previewContentByDocumentId: {},
  stalePatchIds: [],
  patchSourceById: {},
  setPatch: (patch) =>
    set((state) => ({
      patchesByDocumentId: {
        ...state.patchesByDocumentId,
        [patch.documentId]: [
          ...(state.patchesByDocumentId[patch.documentId] ?? []).filter(
            (existingPatch) => existingPatch.id !== patch.id
          ),
          patch,
        ],
      },
      pendingPatchIds:
        patch.status === "pending"
          ? [...new Set([...state.pendingPatchIds, patch.id])]
          : state.pendingPatchIds.filter((pendingPatchId) => pendingPatchId !== patch.id),
      patchSourceById: {
        ...state.patchSourceById,
        [patch.id]: patch.createdBy,
      },
    })),
  setPatchesForDocument: (documentId, patches) =>
    set((state) => ({
      patchesByDocumentId: {
        ...state.patchesByDocumentId,
        [documentId]: patches,
      },
      pendingPatchIds: [
        ...new Set([
          ...state.pendingPatchIds.filter(
            (patchId) => !patches.some((patch) => patch.id === patchId)
          ),
          ...patches
            .filter((patch) => patch.status === "pending")
            .map((patch) => patch.id),
        ]),
      ],
      patchSourceById: {
        ...state.patchSourceById,
        ...Object.fromEntries(patches.map((patch) => [patch.id, patch.createdBy])),
      },
    })),
  selectPatch: (patchId) => set({ selectedPatchId: patchId }),
  setPreviewContent: (documentId, content) =>
    set((state) => ({
      previewContentByDocumentId: {
        ...state.previewContentByDocumentId,
        [documentId]: content,
      },
    })),
  markPatchStale: (patchId) =>
    set((state) => ({
      stalePatchIds: state.stalePatchIds.includes(patchId)
        ? state.stalePatchIds
        : [...state.stalePatchIds, patchId],
    })),
  clearDocumentPatches: (documentId) =>
    set((state) => {
      const nextPatchesByDocumentId = { ...state.patchesByDocumentId };
      const removedPatches = nextPatchesByDocumentId[documentId] ?? [];
      delete nextPatchesByDocumentId[documentId];

      const nextPatchSourceById = { ...state.patchSourceById };
      removedPatches.forEach((patch) => {
        delete nextPatchSourceById[patch.id];
      });

      return {
        patchesByDocumentId: nextPatchesByDocumentId,
        pendingPatchIds: state.pendingPatchIds.filter(
          (patchId) => !removedPatches.some((patch) => patch.id === patchId)
        ),
        selectedPatchId:
          state.selectedPatchId &&
          removedPatches.some((patch) => patch.id === state.selectedPatchId)
            ? null
            : state.selectedPatchId,
        previewContentByDocumentId: {
          ...state.previewContentByDocumentId,
          [documentId]: null,
        },
        stalePatchIds: state.stalePatchIds.filter(
          (patchId) => !removedPatches.some((patch) => patch.id === patchId)
        ),
        patchSourceById: nextPatchSourceById,
      };
    }),
  clearPatches: () =>
    set({
      patchesByDocumentId: {},
      pendingPatchIds: [],
      selectedPatchId: null,
      previewContentByDocumentId: {},
      stalePatchIds: [],
      patchSourceById: {},
    }),
}));
