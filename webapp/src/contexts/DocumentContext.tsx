import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import axios from "axios";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";
import { adaptWorkspaceDocumentToDocumentoOut } from "@/workspace/adapters/documentAdapter";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useAiSessionStore } from "@/workspace/stores/aiSessionStore";
import { sanitizeDocumentContentForSave } from "@/workspace/utils/documentSave";
import { DocumentJsonContent } from "@/workspace/types";

// Define the context type
type DocumentContextType = {
  // State
  documents: DocumentoOut[];
  activeDocument: DocumentoOut | null;
  activeDocumentId: number | null;
  loading: boolean;
  error: string | null;
  isSaving: boolean;
  pendingSave: { id: number; content: string } | null;

  // Actions
  selectDocument: (docId: number) => void;
  saveDocument: (
    docId: number,
    content: string,
    contentJson?: DocumentJsonContent,
  ) => Promise<boolean>;
  createDocument: (
    documentType: string,
    content?: string,
    contentJson?: DocumentJsonContent,
  ) => Promise<DocumentoOut | null>;
  deleteDocument: (docId: number) => Promise<boolean>;
  addDocument: (newDocument: DocumentoOut) => void;
  fetchDocuments: () => Promise<void>;
};

// Create the context with a default undefined value
const DocumentContext = createContext<DocumentContextType | undefined>(
  undefined
);

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.detail ?? error.message ?? fallback;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

// Create the provider
export function DocumentProvider({
  children,
  encounterId,
}: {
  children: React.ReactNode;
  encounterId: number;
}) {
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [pendingSave, setPendingSave] = useState<{
    id: number;
    content: string;
  } | null>(null);

  const documentOrder = useWorkspaceStore((state) => state.documentOrder);
  const documentsById = useWorkspaceStore((state) => state.documentsById);
  const activeWorkspaceDocumentId = useWorkspaceStore(
    (state) => state.activeDocumentId
  );
  const loading = useWorkspaceStore((state) => state.loading);
  const error = useWorkspaceStore((state) => state.error);
  const loadedEncounterId = useWorkspaceStore((state) => state.loadedEncounterId);
  const bootstrapEncounterDocuments = useWorkspaceStore(
    (state) => state.bootstrapEncounterDocuments
  );
  const setActiveDocument = useWorkspaceStore((state) => state.setActiveDocument);
  const addDocumentToWorkspace = useWorkspaceStore((state) => state.addDocument);
  const removeDocumentFromWorkspace = useWorkspaceStore(
    (state) => state.removeDocument
  );
  const upsertDocumentInWorkspace = useWorkspaceStore(
    (state) => state.upsertDocument
  );
  const clearEncounterWorkspace = useWorkspaceStore(
    (state) => state.clearEncounterWorkspace
  );
  const setWorkspaceLoading = useWorkspaceStore(
    (state) => state.setWorkspaceLoading
  );
  const setWorkspaceError = useWorkspaceStore((state) => state.setWorkspaceError);
  const clearSnapshots = useDocumentSnapshotStore(
    (state) => state.clearSnapshots
  );
  const clearDrafts = useDocumentDraftStore((state) => state.clearDrafts);
  const clearDerivedState = useDocumentDerivedStore(
    (state) => state.clearDerivedState
  );
  const clearPatchSets = usePatchSetStore((state) => state.clearAll);
  const clearSession = useAiSessionStore((state) => state.clearSession);

  // Tabs and active document now live in WorkspaceStore; this context remains
  // as a temporary bridge so the rest of the encounter detail can migrate
  // without a flag day refactor.
  const documents = useMemo(
    () =>
      documentOrder
        .map((documentId) => documentsById[documentId])
        .filter(Boolean)
        .map((document) =>
        adaptWorkspaceDocumentToDocumentoOut(document)
      ),
    [documentOrder, documentsById]
  );

  const activeDocument = useMemo(
    () =>
      activeWorkspaceDocumentId && documentsById[activeWorkspaceDocumentId]
        ? adaptWorkspaceDocumentToDocumentoOut(
            documentsById[activeWorkspaceDocumentId]
          )
        : null,
    [activeWorkspaceDocumentId, documentsById]
  );

  const activeDocumentId = activeWorkspaceDocumentId
    ? Number(activeWorkspaceDocumentId)
    : null;

  /**
   * Fetch all documents for an encounter
   */
  const fetchDocuments = useCallback(async () => {
    if (!encounterId || loading) {
      logger.debug(
        `[DOC_CONTEXT] fetchDocuments skipped (encounterId: ${encounterId}, loading: ${loading})`
      );
      return;
    }

    logger.debug(
      `[DOC_CONTEXT] Attempting to fetch documents for encounter ${encounterId}`
    );
    setWorkspaceLoading(true);
    setWorkspaceError(null);

    try {
      const response = await axiosInstance.get(
        `/api/v1/documents/encounter/${encounterId}`
      );
      const data = response.data;

      logger.debug(
        `[DOC_CONTEXT] Successfully fetched ${data.length} documents for encounter ${encounterId}`
      );
      bootstrapEncounterDocuments(encounterId, data);
      setWorkspaceError(null);
    } catch (err: unknown) {
      logger.error(
        `[DOC_CONTEXT] Failed to fetch documents for encounter ${encounterId}:`,
        err
      );
      setWorkspaceError(
        getErrorMessage(err, "Error desconocido al cargar los documentos")
      );
    } finally {
      setWorkspaceLoading(false);
    }
  }, [
    encounterId,
    loading,
    bootstrapEncounterDocuments,
    setWorkspaceError,
    setWorkspaceLoading,
  ]);

  /**
   * Select a document as active
   *
   * @param docId - ID of the document to select
   */
  const selectDocument = useCallback(
    (docId: number) => {
      if (activeDocumentId !== docId) {
        setActiveDocument(String(docId));
      }
    },
    [activeDocumentId, setActiveDocument]
  );

  /**
   * Save document content to the server
   */
  const saveDocument = useCallback(
    async (docId: number, content: string, contentJson?: DocumentJsonContent) => {
      try {
        setIsSaving(true);
        logger.debug(
          `[DOC_SAVE] Document ${docId}: Saving content (${content.length} chars)`
        );

        const finalContent = sanitizeDocumentContentForSave(content);

        logger.debug(
          `[DOC_SAVE] Document ${docId}: Final content length: ${finalContent.length} chars`
        );

        await axiosInstance.patch(`/api/v1/documents/by-editor/${docId}`, {
          content: finalContent,
          content_markdown: finalContent,
          content_json: contentJson ?? null,
        });

        const currentDocument = documents.find((doc) => doc.id === docId);
        if (currentDocument) {
          upsertDocumentInWorkspace(
            {
              ...currentDocument,
              content: finalContent,
              content_markdown: finalContent,
              content_json: contentJson ?? null,
            },
            encounterId
          );
        }

        logger.debug(`[DOC_SAVE ✅] Document ${docId}: Saved successfully`);
        return true;
      } catch (err: unknown) {
        logger.error(`[DOC_SAVE ❌] Document ${docId}: Error saving:`, err);
        setPendingSave({ id: docId, content });
        throw err;
      } finally {
        setIsSaving(false);
      }
    },
    [documents, encounterId, upsertDocumentInWorkspace]
  );

  /**
   * Create a new document for the encounter
   *
   * @param documentType - Type of document to create
   * @param content - Initial content for the document
   * @returns The newly created document
   */
  const createDocument = useCallback(
    async (
      documentType: string,
      content: string = "",
      contentJson?: DocumentJsonContent,
    ) => {
      try {
        setWorkspaceLoading(true);
        const response = await axiosInstance.post("/api/v1/documents", {
          encounter_id: encounterId,
          kind: documentType,
          content,
          content_markdown: content,
          content_json: contentJson ?? null,
        });

        const newDocument = response.data;

        addDocumentToWorkspace(newDocument, encounterId);
        setActiveDocument(String(newDocument.id));

        return newDocument;
      } catch (err: unknown) {
        logger.error("Failed to create document:", err);
        setWorkspaceError(getErrorMessage(err, "Error al crear el documento"));
        return null;
      } finally {
        setWorkspaceLoading(false);
      }
    },
    [encounterId, addDocumentToWorkspace, setActiveDocument, setWorkspaceError, setWorkspaceLoading]
  );

  /**
   * Delete a document
   *
   * @param docId - ID of the document to delete
   * @returns True if deletion was successful
   */
  const deleteDocument = useCallback(
    async (docId: number) => {
      try {
        setWorkspaceLoading(true);
        await axiosInstance.delete(`/api/v1/documents/${docId}`);
        removeDocumentFromWorkspace(String(docId));

        return true;
      } catch (err: unknown) {
        logger.error("Failed to delete document:", err);
        setWorkspaceError(
          getErrorMessage(err, "Error al eliminar el documento")
        );
        return false;
      } finally {
        setWorkspaceLoading(false);
      }
    },
    [removeDocumentFromWorkspace, setWorkspaceError, setWorkspaceLoading]
  );

  const addDocument = useCallback((newDocument: DocumentoOut) => {
    addDocumentToWorkspace(newDocument, encounterId);
  }, [addDocumentToWorkspace, encounterId]);

  const clearEncounterScopedState = useCallback(() => {
    clearSnapshots();
    clearDrafts();
    clearDerivedState();
    clearPatchSets();
    clearSession();
  }, [clearDerivedState, clearDrafts, clearPatchSets, clearSession, clearSnapshots]);

  useEffect(() => {
    if (encounterId) {
      if (String(encounterId) !== loadedEncounterId) {
        logger.debug(
          `[DOC_CONTEXT] Encounter changed to ${encounterId} (previously loaded: ${loadedEncounterId}). Fetching documents.`
        );
        clearEncounterScopedState();
        void fetchDocuments();
      } else {
        logger.debug(
          `[DOC_CONTEXT] Encounter ${encounterId} documents already loaded. Skipping fetch.`
        );
      }
    } else {
      logger.debug(
        `[DOC_CONTEXT] encounterId is null or invalid. Resetting state.`
      );
      clearEncounterScopedState();
      clearEncounterWorkspace();
    }
  }, [
    encounterId,
    loadedEncounterId,
    fetchDocuments,
    clearEncounterScopedState,
    clearEncounterWorkspace,
  ]);

  const value: DocumentContextType = {
    documents,
    activeDocument,
    activeDocumentId,
    loading,
    error,
    isSaving,
    pendingSave,
    selectDocument,
    saveDocument,
    createDocument,
    deleteDocument,
    addDocument,
    fetchDocuments,
  };

  return (
    <DocumentContext.Provider value={value}>
      {children}
    </DocumentContext.Provider>
  );
}

// Create a custom hook for using this context
export function useDocumentContext() {
  const context = useContext(DocumentContext);
  if (context === undefined) {
    throw new Error(
      "useDocumentContext must be used within a DocumentProvider"
    );
  }
  return context;
}
