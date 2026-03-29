import { useState, useEffect, useCallback, useRef } from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";

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

  // Track which documents have been loaded to avoid unnecessary refreshes
  const loadedDocumentsRef = useRef<Set<number>>(new Set());

  /**
   * Fetch all documents for an encounter
   */
  const fetchDocuments = useCallback(async () => {
    if (!encounterId) return;

    try {
      setLoading(true);
      const response = await axiosInstance.get(
        `/api/documents/encounter/${encounterId}`
      );

      const data = response.data;
      setDocuments(data);

      // Set the first document as active if available, using the same sorting criteria as TabBar
      if (data.length > 0 && !activeDocumentId) {
        // Sort documents by date and ID before selecting the first one
        const sortedDocs = [...data].sort((a, b) => {
          const dateA = new Date(a.created_on).getTime();
          const dateB = new Date(b.created_on).getTime();

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
      logger.error("Failed to fetch documents:", err);
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
      logger.debug(
        `[DOC_FETCH] Request for document ${docId}, forceRefresh: ${forceRefresh}`
      );
      logger.debug(
        `[CACHE_STATUS] Size: ${
          documentContentCache.size
        } documents, Loaded docs: ${Array.from(loadedDocumentsRef.current).join(
          ", "
        )}`
      );

      // Mark this document as loaded
      const isFirstLoad = !loadedDocumentsRef.current.has(docId);

      // Only force refresh on first load for this document
      const shouldForceRefresh = isFirstLoad && forceRefresh;

      if (isFirstLoad) {
        logger.debug(
          `[DOC_LOAD ⚠️] Document ${docId}: First time loading this document`
        );
      } else {
        logger.debug(
          `[DOC_LOAD ℹ️] Document ${docId}: Document was previously loaded`
        );
      }

      // Return cached content if available and not force refreshing
      if (!shouldForceRefresh && documentContentCache.has(docId)) {
        const cachedContent = documentContentCache.get(docId);
        if (cachedContent && cachedContent.trim().length > 0) {
          logger.debug(
            `[CACHE_HIT ✅] Document ${docId}: Using cached content (${cachedContent.length} chars)`
          );
          // Mark document as loaded even when using cache
          loadedDocumentsRef.current.add(docId);
          return cachedContent;
        }
        logger.debug(
          `[CACHE_INVALID ⚠️] Document ${docId}: Cache entry exists but is empty, fetching from database`
        );
        // If cached content is empty, proceed with fetching
      } else {
        if (shouldForceRefresh) {
          logger.debug(
            `[CACHE_BYPASS ⏭️] Document ${docId}: Force refresh requested (first load)`
          );
        } else if (forceRefresh) {
          logger.debug(
            `[CACHE_IGNORE ℹ️] Document ${docId}: Force refresh requested but document already loaded, using cache`
          );
        } else {
          logger.debug(`[CACHE_MISS ❌] Document ${docId}: Not in cache`);
        }
      }

      try {
        setIsLoadingContent(true);
        logger.debug(`[DB_FETCH 🔍] Document ${docId}: Fetching from database`);

        const response = await axiosInstance.get(`/api/documents/${docId}`);

        const documentData = response.data;
        const content = documentData.content || "";

        logger.debug(
          `[DB_FETCH ✅] Document ${docId}: Received ${content.length} chars from database`
        );

        // Mark this document as loaded after successful fetch
        loadedDocumentsRef.current.add(docId);

        // Only cache non-empty content
        if (content.trim().length > 0) {
          logger.debug(
            `[CACHE_UPDATE 📝] Document ${docId}: Storing content in cache`
          );
          setDocumentContentCache((prev) => {
            const newCache = new Map(prev);
            newCache.set(docId, content);
            logger.debug(
              `[CACHE_STATUS] Updated size: ${newCache.size} documents`
            );
            return newCache;
          });
        } else {
          logger.debug(
            `[CACHE_SKIP ⚠️] Document ${docId}: Not caching empty content`
          );
        }

        return content;
      } catch (err: any) {
        logger.error(`[DB_FETCH ❌] Document ${docId}: Failed to fetch:`, err);
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
  const saveDocument = useCallback(
    async (docId: number, content: string) => {
      // Normalize line breaks before comparing
      const normalizeBreaks = (text: string): string => {
        return text
          .replace(/\r\n/g, "\n")
          .replace(/\r/g, "\n")
          .replace(/\n\n/g, "\n")
          .trim();
      };

      try {
        // Check if content in cache is the same (if available)
        const cachedContent = documentContentCache.get(docId);
        if (
          cachedContent &&
          normalizeBreaks(cachedContent) === normalizeBreaks(content)
        ) {
          logger.debug(
            `[DOC_SAVE] Document ${docId}: Content unchanged from cache, skipping API call`
          );
          return true; // Return success without API call
        }

        setIsSaving(true);
        logger.debug(
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
            logger.debug(`[DOC_SAVE] Document ${docId}: Stripped HTML tags`);
          } catch (e) {
            // Fallback: Use regex to strip HTML tags
            finalContent = content.replace(/<[^>]*>/g, "");
            logger.debug(
              `[DOC_SAVE] Document ${docId}: Stripped HTML tags (regex fallback)`
            );
          }
        }

        logger.debug(
          `[DOC_SAVE] Document ${docId}: Final content length: ${finalContent.length} chars`
        );

        // Send the update
        await axiosInstance.patch(`/api/documents/by-editor/${docId}`, {
          content: finalContent,
        });

        // Update local document data
        setDocuments((docs) =>
          docs.map((doc) =>
            doc.id === docId ? { ...doc, content: finalContent } : doc
          )
        );

        // Update the cache
        logger.debug(`[CACHE_UPDATE 📝] Document ${docId}: Updating after save`);
        setDocumentContentCache((prev) => {
          const newCache = new Map(prev);
          newCache.set(docId, finalContent);
          logger.debug(
            `[CACHE_STATUS] Size after save: ${newCache.size} documents`
          );
          return newCache;
        });

        logger.debug(`[DOC_SAVE ✅] Document ${docId}: Saved successfully`);
        return true;
      } catch (err: any) {
        logger.error(`[DOC_SAVE ❌] Document ${docId}: Error saving:`, err);
        // Store failed save for retry
        setPendingSave({ id: docId, content });
        throw err; // Re-throw to allow handling in components
      } finally {
        setIsSaving(false);
      }
    },
    [documentContentCache]
  );

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
        const response = await axiosInstance.post("/api/documents", {
          encounter_id: encounterId,
          kind: documentType,
          content,
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
        logger.error("Failed to create document:", err);
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
        await axiosInstance.delete(`/api/documents/${docId}`);

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
        logger.error("Failed to delete document:", err);
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

  // Track if this is the initial mount of the component
  const isInitialMount = useRef(true);

  // Load documents when encounterId changes and clear the cache
  useEffect(() => {
    if (encounterId) {
      if (isInitialMount.current) {
        // Clear the content cache and loaded documents on initial mount or when encounter changes
        logger.debug(
          `[CACHE_CLEAR 🧹] Encounter ${encounterId}: Clearing cache on initial load`
        );
        setDocumentContentCache(new Map());
        loadedDocumentsRef.current.clear();
        isInitialMount.current = false;
      } else {
        logger.debug(
          `[CACHE_MAINTAIN] Encounter ${encounterId}: Keeping cache for encounter`
        );
      }
      fetchDocuments();
    }

    // Add a cleanup function to clear cache ONLY when component fully unmounts
    // or when encounter changes
    return () => {
      // Only clear cache if encounter ID changes, not on simple re-renders
      if (encounterId) {
        logger.debug(
          `[CACHE_NOTE] Cleanup function called for encounter ${encounterId}`
        );

        // We'll move the actual cache clearing logic to the next render with a new encounter ID
        // This prevents clearing during tab changes
      }
    };
  }, [encounterId, fetchDocuments]);

  // Additional effect to clear cache when component fully unmounts
  useEffect(() => {
    return () => {
      logger.debug(
        `[CACHE_CLEAR 🧹] Component fully unmounting, clearing cache`
      );
      setDocumentContentCache(new Map());
    };
  }, []);

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
    loadedDocumentIds: Array.from(loadedDocumentsRef.current),

    // Actions
    fetchDocuments,
    addDocument,
    selectDocument,
    saveDocument,
    createDocument,
    deleteDocument,
    fetchDocumentContent,
  };
};
