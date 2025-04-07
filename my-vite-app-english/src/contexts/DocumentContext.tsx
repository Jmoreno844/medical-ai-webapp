import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/commons/utils/axiosInstance";

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
  saveDocument: (docId: number, content: string) => Promise<boolean>;
  createDocument: (
    documentType: string,
    content?: string
  ) => Promise<DocumentoOut | null>;
  deleteDocument: (docId: number) => Promise<boolean>;
  addDocument: (newDocument: DocumentoOut) => void;
  fetchDocuments: () => Promise<void>;
};

// Create the context with a default undefined value
const DocumentContext = createContext<DocumentContextType | undefined>(
  undefined
);

// Create the provider
export function DocumentProvider({
  children,
  encounterId,
}: {
  children: React.ReactNode;
  encounterId: number;
}) {
  const [documents, setDocuments] = useState<DocumentoOut[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(false); // Changed initial state to false
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [pendingSave, setPendingSave] = useState<{
    id: number;
    content: string;
  } | null>(null);

  // Track if this is the initial mount of the component
  const isInitialMount = useRef(true);

  // Add ref to track loaded encounter
  const loadedEncounterIdRef = useRef<number | null>(null);

  /**
   * Fetch all documents for an encounter
   */
  const fetchDocuments = useCallback(async () => {
    if (!encounterId || loading) {
      console.log(
        `[DOC_CONTEXT] fetchDocuments skipped (encounterId: ${encounterId}, loading: ${loading})`
      );
      return;
    }

    console.log(
      `[DOC_CONTEXT] Attempting to fetch documents for encounter ${encounterId}`
    );
    setLoading(true);
    setError(null);

    try {
      const response = await axiosInstance.get(
        `/api/documento/encuentro/${encounterId}`
      );
      const data = response.data;

      console.log(
        `[DOC_CONTEXT] Successfully fetched ${data.length} documents for encounter ${encounterId}`
      );
      setDocuments(data);
      loadedEncounterIdRef.current = encounterId;

      setActiveDocumentId((prevActiveId) => {
        if (data.length > 0 && !prevActiveId) {
          const sortedDocs = [...data].sort((a, b) => {
            const dateA = new Date(a.fecha_creacion).getTime();
            const dateB = new Date(b.fecha_creacion).getTime();
            if (dateA !== dateB) return dateA - dateB;
            return a.id - b.id;
          });
          return sortedDocs[0].id;
        }
        return prevActiveId;
      });

      setError(null);
    } catch (err: any) {
      console.error(
        `[DOC_CONTEXT] Failed to fetch documents for encounter ${encounterId}:`,
        err
      );
      setError(
        err.response?.data?.detail ||
          err.message ||
          "Error desconocido al cargar los documentos"
      );
      loadedEncounterIdRef.current = null;
    } finally {
      setLoading(false);
    }
  }, [encounterId, loading]);

  /**
   * Select a document as active
   *
   * @param docId - ID of the document to select
   */
  const selectDocument = useCallback(
    (docId: number) => {
      if (activeDocumentId !== docId) {
        setActiveDocumentId(docId);
      }
    },
    [activeDocumentId]
  );

  /**
   * Save document content to the server
   */
  const saveDocument = useCallback(async (docId: number, content: string) => {
    try {
      setIsSaving(true);
      console.log(
        `[DOC_SAVE] Document ${docId}: Saving content (${content.length} chars)`
      );

      // Final content preparation - strip all HTML if it exists
      let finalContent = content;

      // If content appears to have any HTML tags, completely strip them
      if (finalContent.includes("<") && finalContent.includes(">")) {
        try {
          // Use DOM to strip all HTML
          const tempDiv = document.createElement("div");
          tempDiv.innerHTML = content;
          finalContent = tempDiv.textContent || "";
          console.log(`[DOC_SAVE] Document ${docId}: Stripped HTML tags`);
        } catch (e) {
          // Fallback: Use regex to strip HTML tags
          finalContent = content.replace(/<[^>]*>/g, "");
          console.log(
            `[DOC_SAVE] Document ${docId}: Stripped HTML tags (regex fallback)`
          );
        }
      }

      console.log(
        `[DOC_SAVE] Document ${docId}: Final content length: ${finalContent.length} chars`
      );

      // Send the update
      const response = await axiosInstance.patch(
        `/api/documento_by_editor/${docId}`,
        {
          contenido: finalContent,
        }
      );

      // Update local document data
      setDocuments((docs) =>
        docs.map((doc) =>
          doc.id === docId ? { ...doc, contenido: finalContent } : doc
        )
      );

      console.log(`[DOC_SAVE ✅] Document ${docId}: Saved successfully`);
      return true;
    } catch (err: any) {
      console.error(`[DOC_SAVE ❌] Document ${docId}: Error saving:`, err);
      // Store failed save for retry
      setPendingSave({ id: docId, content });
      throw err; // Re-throw to allow handling in components
    } finally {
      setIsSaving(false);
    }
  }, []);

  /**
   * Create a new document for the encounter
   *
   * @param documentType - Type of document to create
   * @param content - Initial content for the document
   * @returns The newly created document
   */
  const createDocument = useCallback(
    async (documentType: string, content: string = "") => {
      try {
        setLoading(true);
        const response = await axiosInstance.post("/api/documento/", {
          id_encuentro: encounterId,
          tipo: documentType,
          contenido: content,
        });

        const newDocument = response.data;

        // Update documents list with the new document
        setDocuments((docs) => [...docs, newDocument]);

        // Select the new document
        setActiveDocumentId(newDocument.id);

        return newDocument;
      } catch (err: any) {
        console.error("Failed to create document:", err);
        setError(
          err.response?.data?.detail ||
            err.message ||
            "Error al crear el documento"
        );
        return null;
      } finally {
        setLoading(false);
      }
    },
    [encounterId]
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
        setLoading(true);
        await axiosInstance.delete(`/api/documento/${docId}`);

        // Remove document from local state
        setDocuments((docs) => docs.filter((doc) => doc.id !== docId));

        // If we deleted the active document, select another one
        if (activeDocumentId === docId) {
          const remainingDocs = documents.filter((doc) => doc.id !== docId);
          setActiveDocumentId(
            remainingDocs.length > 0 ? remainingDocs[0].id : null
          );
        }

        return true;
      } catch (err: any) {
        console.error("Failed to delete document:", err);
        setError(
          err.response?.data?.detail ||
            err.message ||
            "Error al eliminar el documento"
        );
        return false;
      } finally {
        setLoading(false);
      }
    },
    [activeDocumentId, documents]
  );

  // Add a function to add a new document to the documents list
  const addDocument = useCallback((newDocument: DocumentoOut) => {
    setDocuments((prev) => [...prev, newDocument]);
  }, []);

  // Load documents when encounterId changes AND check loaded ref
  useEffect(() => {
    if (encounterId) {
      if (encounterId !== loadedEncounterIdRef.current) {
        console.log(
          `[DOC_CONTEXT] Encounter changed to ${encounterId} (previously loaded: ${loadedEncounterIdRef.current}). Fetching documents.`
        );
        fetchDocuments(); // Initiate fetch
      } else {
        console.log(
          `[DOC_CONTEXT] Encounter ${encounterId} documents already loaded. Skipping fetch.`
        );
        // Ensure loading state is correct if we skipped fetch but it might have been true
        if (loading) setLoading(false);
      }
    } else {
      // Handle encounterId becoming null/invalid
      console.log(
        `[DOC_CONTEXT] encounterId is null or invalid. Resetting state.`
      );
      setDocuments([]);
      setActiveDocumentId(null);
      loadedEncounterIdRef.current = null;
      setLoading(false); // Ensure loading is false
      setError(null);
    }

    // Cleanup function (optional) - no changes needed here
    return () => {
      // console.log(`[DOC_CONTEXT] Cleanup for encounter effect (current encounterId: ${encounterId})`);
    };
  }, [encounterId, fetchDocuments]); // NEW - Corrected dependency array

  // Get the active document
  const activeDocument =
    documents.find((doc) => doc.id === activeDocumentId) || null;

  // Create the context value
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
