import { useState, useEffect, useCallback } from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/utils/axiosInstance";

/**
 * Custom hook for managing medical documents
 *
 * Provides functionality for fetching, selecting, and saving documents
 *
 * @param encounterId - ID of the encounter to fetch documents for
 * @returns Document state and handlers
 */
export const useDocuments = (encounterId: number) => {
  const [documents, setDocuments] = useState<DocumentoOut[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [pendingSave, setPendingSave] = useState<{
    id: number;
    content: string;
  } | null>(null);
  // Add document content cache
  const [documentContentCache, setDocumentContentCache] = useState<
    Map<number, string>
  >(new Map());
  const [isLoadingContent, setIsLoadingContent] = useState<boolean>(false);

  /**
   * Fetch all documents for an encounter
   */
  const fetchDocuments = useCallback(async () => {
    if (!encounterId) return;

    try {
      setLoading(true);
      const response = await axiosInstance.get(
        `/api/documento/encuentro/${encounterId}`
      );

      const data = response.data;
      setDocuments(data);

      // Set the first document as active if available, using the same sorting criteria as TabBar
      if (data.length > 0 && !activeDocumentId) {
        // Sort documents by date and ID before selecting the first one
        const sortedDocs = [...data].sort((a, b) => {
          const dateA = new Date(a.fecha_creacion).getTime();
          const dateB = new Date(b.fecha_creacion).getTime();

          // If dates are different, sort by date
          if (dateA !== dateB) {
            return dateA - dateB;
          }

          // If dates are the same, use ID as a tiebreaker
          return a.id - b.id;
        });

        // Select the first document from the sorted array
        setActiveDocumentId(sortedDocs[0].id);
      }
    } catch (err: any) {
      console.error("Failed to fetch documents:", err);
      setError(
        err.response?.data?.detail ||
          err.message ||
          "Error desconocido al cargar los documentos"
      );
    } finally {
      setLoading(false);
    }
  }, [encounterId, activeDocumentId]);

  /**
   * Fetch content for a specific document
   * @param docId - Document ID to fetch content for
   * @returns Document content or null if there was an error
   */
  const fetchDocumentContent = useCallback(
    async (docId: number, forceRefresh = false) => {
      // Return cached content if available and not force refreshing
      if (!forceRefresh && documentContentCache.has(docId)) {
        const cachedContent = documentContentCache.get(docId);
        if (cachedContent && cachedContent.trim().length > 0) {
          console.log(`Using cached content for document ${docId}`);
          return cachedContent;
        }
        // If cached content is empty, proceed with fetching
      }

      try {
        setIsLoadingContent(true);
        const response = await axiosInstance.get(`/api/documento/${docId}`);
        console.log("Fetching document content from API");
        const documentData = response.data;
        const content = documentData.contenido || "";

        // Only cache non-empty content
        if (content.trim().length > 0) {
          // Cache the content
          setDocumentContentCache((prev) => {
            const newCache = new Map(prev);
            newCache.set(docId, content);
            return newCache;
          });
        }

        return content;
      } catch (err: any) {
        console.error(`Failed to fetch content for document ${docId}:`, err);
        setError(
          err.response?.data?.detail ||
            err.message ||
            "Error al cargar el contenido del documento"
        );
        return null;
      } finally {
        setIsLoadingContent(false);
      }
    },
    [documentContentCache]
  );

  /**
   * Select a document as active
   *
   * @param docId - ID of the document to select
   */
  const selectDocument = useCallback(
    (docId: number) => {
      if (activeDocumentId !== docId) {
        setActiveDocumentId(docId);

        // Always fetch content when selecting a document
        // Use the cache only for rapid tab switching
        fetchDocumentContent(docId, false);
      }
    },
    [activeDocumentId, fetchDocumentContent]
  );

  /**
   * Save document content to the server
   */
  const saveDocument = useCallback(async (docId: number, content: string) => {
    try {
      setIsSaving(true);

      // Log the incoming content
      console.log(`API: Saving document ${docId} content...`);
      console.log("Original content:", content);

      // Final content preparation - strip all HTML if it exists
      let finalContent = content;

      // If content appears to have any HTML tags, completely strip them
      if (finalContent.includes("<") && finalContent.includes(">")) {
        try {
          // Use DOM to strip all HTML
          const tempDiv = document.createElement("div");
          tempDiv.innerHTML = content;
          finalContent = tempDiv.textContent || "";
        } catch (e) {
          // Fallback: Use regex to strip HTML tags
          finalContent = content.replace(/<[^>]*>/g, "");
        }
      }

      console.log("Final content to save:", finalContent);

      // Send the update
      const response = await axiosInstance.patch(`/api/documento/${docId}`, {
        contenido: finalContent,
      });

      // Update local document data
      setDocuments((docs) =>
        docs.map((doc) =>
          doc.id === docId ? { ...doc, contenido: finalContent } : doc
        )
      );

      // Update the cache
      setDocumentContentCache((prev) => {
        const newCache = new Map(prev);
        newCache.set(docId, finalContent);
        return newCache;
      });

      console.log(`API: Document ${docId} saved successfully`);
      return true;
    } catch (err: any) {
      console.error("API: Error saving document:", err);
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

        // Add new document to cache
        setDocumentContentCache((prev) => {
          const newCache = new Map(prev);
          newCache.set(newDocument.id, content);
          return newCache;
        });

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

        // Remove from cache
        setDocumentContentCache((prev) => {
          const newCache = new Map(prev);
          newCache.delete(docId);
          return newCache;
        });

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

  // Load documents when encounterId changes and clear the cache
  useEffect(() => {
    if (encounterId) {
      // Clear the content cache when changing encounters or on initial load
      setDocumentContentCache(new Map());
      fetchDocuments();
    }

    // Add a cleanup function to clear cache when component unmounts
    return () => {
      setDocumentContentCache(new Map());
    };
  }, [encounterId, fetchDocuments]);

  // Get currently active document
  const activeDocument =
    documents.find((doc) => doc.id === activeDocumentId) || null;

  return {
    // State
    documents,
    activeDocument,
    activeDocumentId,
    loading,
    error,
    isSaving,
    pendingSave,
    isLoadingContent,
    documentContentCache,

    // Actions
    fetchDocuments,
    selectDocument,
    saveDocument,
    createDocument,
    deleteDocument,
    fetchDocumentContent,
  };
};
