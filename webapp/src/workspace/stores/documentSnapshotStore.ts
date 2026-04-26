import axios from "axios";
import { create } from "zustand";
import axiosInstance from "@/commons/utils/axiosInstance";
import { DocumentJsonContent, DocumentSnapshot } from "@/workspace/types";

type DocumentSnapshotStoreState = {
  snapshotsByDocumentId: Record<string, DocumentSnapshot | null>;
  isLoadingByDocumentId: Record<string, boolean>;
  fetchErrorByDocumentId: Record<string, string | null>;
  loadedDocumentIds: string[];
  getSnapshot: (documentId: string) => DocumentSnapshot | null;
  setSnapshot: (
    documentId: string,
    contentMarkdown: string,
    contentJson?: DocumentJsonContent,
    version?: number
  ) => void;
  fetchSnapshot: (
    documentId: string,
    forceRefresh?: boolean
  ) => Promise<DocumentSnapshot | null>;
  markSnapshotLoaded: (documentId: string) => void;
  setSnapshotLoading: (documentId: string, isLoading: boolean) => void;
  setSnapshotError: (documentId: string, error: string | null) => void;
  clearSnapshots: () => void;
};

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return (
      error.response?.data?.detail ??
      error.message ??
      "Error al cargar el snapshot del documento"
    );
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Error al cargar el snapshot del documento";
}

export const useDocumentSnapshotStore =
  create<DocumentSnapshotStoreState>((set, get) => ({
    snapshotsByDocumentId: {},
    isLoadingByDocumentId: {},
    fetchErrorByDocumentId: {},
    loadedDocumentIds: [],
    getSnapshot: (documentId) => get().snapshotsByDocumentId[documentId] ?? null,
    setSnapshot: (documentId, contentMarkdown, contentJson, version) =>
      set((state) => {
        const existingSnapshot = state.snapshotsByDocumentId[documentId];
        const nextVersion =
          version ??
          (existingSnapshot
            ? existingSnapshot.contentMarkdown === contentMarkdown
              ? existingSnapshot.version
              : existingSnapshot.version + 1
            : 1);

        return {
          snapshotsByDocumentId: {
            ...state.snapshotsByDocumentId,
            [documentId]: {
              documentId,
              version: nextVersion,
              contentMarkdown,
              contentJson: typeof contentJson === "undefined" ? null : contentJson,
              savedAt: new Date().toISOString(),
            },
          },
          fetchErrorByDocumentId: {
            ...state.fetchErrorByDocumentId,
            [documentId]: null,
          },
          loadedDocumentIds: state.loadedDocumentIds.includes(documentId)
            ? state.loadedDocumentIds
            : [...state.loadedDocumentIds, documentId],
        };
      }),
    fetchSnapshot: async (documentId, forceRefresh = false) => {
      const cachedSnapshot = get().snapshotsByDocumentId[documentId];
      if (cachedSnapshot && !forceRefresh) {
        return cachedSnapshot;
      }

      get().setSnapshotLoading(documentId, true);
      get().setSnapshotError(documentId, null);

      try {
        const response = await axiosInstance.get(`/api/v1/documents/${documentId}`);
        const contentMarkdown =
          response.data.content_markdown ?? response.data.content ?? "";
        const contentJson =
          typeof response.data.content_json === "undefined"
            ? null
            : (response.data.content_json as DocumentJsonContent);
        const snapshot: DocumentSnapshot = {
          documentId,
          version: 1,
          contentMarkdown,
          contentJson,
          savedAt: new Date().toISOString(),
        };

        set((state) => ({
          snapshotsByDocumentId: {
            ...state.snapshotsByDocumentId,
            [documentId]: snapshot,
          },
        }));
        get().markSnapshotLoaded(documentId);
        return snapshot;
      } catch (error) {
        get().setSnapshotError(documentId, getErrorMessage(error));
        return null;
      } finally {
        get().setSnapshotLoading(documentId, false);
      }
    },
    markSnapshotLoaded: (documentId) =>
      set((state) => ({
        loadedDocumentIds: state.loadedDocumentIds.includes(documentId)
          ? state.loadedDocumentIds
          : [...state.loadedDocumentIds, documentId],
      })),
    setSnapshotLoading: (documentId, isLoading) =>
      set((state) => ({
        isLoadingByDocumentId: {
          ...state.isLoadingByDocumentId,
          [documentId]: isLoading,
        },
      })),
    setSnapshotError: (documentId, error) =>
      set((state) => ({
        fetchErrorByDocumentId: {
          ...state.fetchErrorByDocumentId,
          [documentId]: error,
        },
      })),
    clearSnapshots: () =>
      set({
        snapshotsByDocumentId: {},
        isLoadingByDocumentId: {},
        fetchErrorByDocumentId: {},
        loadedDocumentIds: [],
      }),
  }));
