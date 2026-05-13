import { create } from "zustand";
import { DocumentDerivedState, TranscriptionBlock } from "@/workspace/types";

type DocumentDerivedStoreState = {
  derivedByDocumentId: Record<string, DocumentDerivedState | null>;
  activeGenerationDocumentId: string | null;
  activeTranscriptionDocumentId: string | null;
  getDerivedState: (documentId: string) => DocumentDerivedState | null;
  setDerivedState: (derivedState: DocumentDerivedState) => void;
  startGeneration: (documentId: string) => void;
  setGenerationProcessingId: (
    documentId: string,
    processingId: string | null
  ) => void;
  updateGenerationContent: (
    documentId: string,
    streamingContent: string
  ) => void;
  completeGeneration: (documentId: string, finalContent?: string) => void;
  failGeneration: (documentId: string, error: string) => void;
  startTranscription: (
    documentId: string,
    initialContent?: string,
    transcriptionBlocks?: TranscriptionBlock[],
  ) => void;
  updateTranscriptionContent: (
    documentId: string,
    streamingContent: string,
    transcriptionBlocks?: TranscriptionBlock[],
  ) => void;
  completeTranscription: (
    documentId: string,
    finalContent?: string,
    transcriptionBlocks?: TranscriptionBlock[],
  ) => void;
  failTranscription: (documentId: string, error: string) => void;
  setPatchPreview: (documentId: string, previewContent: string) => void;
  clearPatchPreview: (documentId: string) => void;
  clearDocumentDerivedState: (documentId: string) => void;
  clearDerivedState: () => void;
};

function createEmptyDerivedState(
  documentId: string,
  overrides: Partial<DocumentDerivedState> = {}
): DocumentDerivedState {
  return {
    documentId,
    editorMode: "edit",
    inProgress: false,
    isComplete: false,
    error: null,
    updatedAt: new Date().toISOString(),
    transcriptionStatus: "idle",
    ...overrides,
  };
}

export const useDocumentDerivedStore =
  create<DocumentDerivedStoreState>((set, get) => ({
    derivedByDocumentId: {},
    activeGenerationDocumentId: null,
    activeTranscriptionDocumentId: null,
    getDerivedState: (documentId) => get().derivedByDocumentId[documentId] ?? null,
    setDerivedState: (derivedState) =>
      set((state) => ({
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [derivedState.documentId]: derivedState,
        },
      })),
    startGeneration: (documentId) =>
      set((state) => ({
        activeGenerationDocumentId: documentId,
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: {
            ...state.derivedByDocumentId[documentId],
            ...createEmptyDerivedState(documentId, {
              editorMode: "streaming_preview",
              source: "generation",
              inProgress: true,
              streamingContent: "",
            }),
          },
        },
      })),
    setGenerationProcessingId: (documentId, processingId) =>
      set((state) => ({
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "streaming_preview",
            source: "generation",
            inProgress: true,
            processingId,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    updateGenerationContent: (documentId, streamingContent) =>
      set((state) => ({
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "streaming_preview",
            source: "generation",
            inProgress: true,
            error: null,
            streamingContent,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    completeGeneration: (documentId, finalContent) =>
      set((state) => ({
        activeGenerationDocumentId: documentId,
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "edit",
            source: "generation",
            inProgress: false,
            isComplete: true,
            error: null,
            streamingContent:
              finalContent ?? state.derivedByDocumentId[documentId]?.streamingContent,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    failGeneration: (documentId, error) =>
      set((state) => ({
        activeGenerationDocumentId: documentId,
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "edit",
            source: "generation",
            inProgress: false,
            isComplete: false,
            error,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    startTranscription: (documentId, initialContent, transcriptionBlocks) =>
      set((state) => ({
        activeTranscriptionDocumentId: documentId,
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "streaming_preview",
              source: "transcription",
              inProgress: true,
              transcriptionStatus: "pending",
              transcriptionBlocks:
                transcriptionBlocks ??
                state.derivedByDocumentId[documentId]?.transcriptionBlocks,
              streamingContent:
                initialContent ??
                state.derivedByDocumentId[documentId]?.streamingContent ??
              "",
          }),
        },
      })),
    updateTranscriptionContent: (
      documentId,
      streamingContent,
      transcriptionBlocks,
    ) =>
      set((state) => ({
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "streaming_preview",
            source: "transcription",
            inProgress: true,
            transcriptionStatus: "pending",
            error: null,
            streamingContent,
            transcriptionBlocks:
              transcriptionBlocks ??
              state.derivedByDocumentId[documentId]?.transcriptionBlocks,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    completeTranscription: (documentId, finalContent, transcriptionBlocks) =>
      set((state) => ({
        activeTranscriptionDocumentId: documentId,
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "read_only",
            source: "transcription",
            inProgress: false,
            isComplete: true,
            error: null,
            transcriptionStatus: "success",
            transcriptionBlocks:
              transcriptionBlocks ??
              state.derivedByDocumentId[documentId]?.transcriptionBlocks,
            streamingContent:
              finalContent ?? state.derivedByDocumentId[documentId]?.streamingContent,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    failTranscription: (documentId, error) =>
      set((state) => ({
        activeTranscriptionDocumentId: documentId,
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "read_only",
            source: "transcription",
            inProgress: false,
            isComplete: false,
            error,
            transcriptionStatus: "error",
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    setPatchPreview: (documentId, previewContent) =>
      set((state) => ({
        derivedByDocumentId: {
          ...state.derivedByDocumentId,
          [documentId]: createEmptyDerivedState(documentId, {
            ...state.derivedByDocumentId[documentId],
            editorMode: "patch_review",
            source: "patch_review",
            patchPreviewContent: previewContent,
            inProgress: false,
            updatedAt: new Date().toISOString(),
          }),
        },
      })),
    clearPatchPreview: (documentId) =>
      set((state) => {
        const existingState = state.derivedByDocumentId[documentId];
        if (!existingState) {
          return state;
        }

        return {
          derivedByDocumentId: {
            ...state.derivedByDocumentId,
            [documentId]: {
              ...existingState,
              editorMode: "edit",
              patchPreviewContent: undefined,
              source:
                existingState.source === "patch_review"
                  ? "system"
                  : existingState.source,
              updatedAt: new Date().toISOString(),
            },
          },
        };
      }),
    clearDocumentDerivedState: (documentId) =>
      set((state) => {
        const nextDerivedByDocumentId = { ...state.derivedByDocumentId };
        delete nextDerivedByDocumentId[documentId];

        return {
          derivedByDocumentId: nextDerivedByDocumentId,
          activeGenerationDocumentId:
            state.activeGenerationDocumentId === documentId
              ? null
              : state.activeGenerationDocumentId,
          activeTranscriptionDocumentId:
            state.activeTranscriptionDocumentId === documentId
              ? null
              : state.activeTranscriptionDocumentId,
        };
      }),
    clearDerivedState: () =>
      set({
        derivedByDocumentId: {},
        activeGenerationDocumentId: null,
        activeTranscriptionDocumentId: null,
      }),
  }));
