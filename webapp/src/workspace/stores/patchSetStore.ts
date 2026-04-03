import { create } from "zustand";
import { CopilotPatchSetResponse, CopilotPatchStatus } from "../../features/copilotDebug/types";

interface PatchSetState {
  activePatchSetId: string | null;
  patchSets: Record<string, CopilotPatchSetResponse>;
  selectedPatchId: string | null;

  // Actions
  addPatchSet: (patchSet: CopilotPatchSetResponse) => void;
  removePatchSet: (id: string) => void;
  setActivePatchSet: (id: string | null) => void;
  setSelectedPatch: (id: string | null) => void;
  updatePatchStatus: (patchSetId: string, patchId: string, status: CopilotPatchStatus) => void;
  clearAll: () => void;
}

export const usePatchSetStore = create<PatchSetState>((set) => ({
  activePatchSetId: null,
  patchSets: {},
  selectedPatchId: null,

  addPatchSet: (patchSet) =>
    set((state) => ({
      patchSets: {
        ...state.patchSets,
        [patchSet.id]: patchSet,
      },
    })),

  removePatchSet: (id) =>
    set((state) => {
      const newPatchSets = { ...state.patchSets };
      delete newPatchSets[id];
      return {
        patchSets: newPatchSets,
        activePatchSetId: state.activePatchSetId === id ? null : state.activePatchSetId,
        selectedPatchId: state.selectedPatchId && state.patchSets[id]?.patches.some(p => p.id === state.selectedPatchId) ? null : state.selectedPatchId,
      };
    }),

  setActivePatchSet: (id) => set({ activePatchSetId: id }),

  setSelectedPatch: (id) => set({ selectedPatchId: id }),

  updatePatchStatus: (patchSetId, patchId, status) =>
    set((state) => {
      const patchSet = state.patchSets[patchSetId];
      if (!patchSet) return state;

      const updatedPatches = patchSet.patches.map((p) =>
        p.id === patchId ? { ...p, status } : p
      );

      return {
        patchSets: {
          ...state.patchSets,
          [patchSetId]: {
            ...patchSet,
            patches: updatedPatches,
          },
        },
      };
    }),

  clearAll: () =>
    set({
      activePatchSetId: null,
      patchSets: {},
      selectedPatchId: null,
    }),
}));
