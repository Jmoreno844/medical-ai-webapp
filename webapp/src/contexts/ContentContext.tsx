import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { useDocumentContext } from "./DocumentContext";
import { logger } from "@/lib/logger";

// Define the context type
type ContentContextType = {
  // State
  documentContent: string;
  isLoadingContent: boolean;
  fetchError: string | null;
  contentLoadedSuccessfully: boolean;
  documentContentCache: Map<number, string>;
  editorRefreshTrigger: number;
  loadedDocumentIds: number[];

  // Actions
  fetchDocumentContent: (
    docId: number,
    forceRefresh?: boolean
  ) => Promise<string | null>;
  reloadContent: (forceRefresh?: boolean) => Promise<void>;
  triggerEditorRefresh: () => void;
  saveContent: (docId: number, content: string) => Promise<boolean>;
  updateDocumentContent: (docId: number, content: string) => void; // New function
};

// Create the context
const ContentContext = createContext<ContentContextType | undefined>(undefined);

// Create the provider
export function ContentProvider({ children }: { children: React.ReactNode }) {
  const { activeDocumentId, saveDocument } = useDocumentContext();

  const [documentContent, setDocumentContent] = useState<string>("");
  const [isLoadingContent, setIsLoadingContent] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [contentLoadedSuccessfully, setContentLoadedSuccessfully] =
    useState<boolean>(false);
  const [documentContentCache, setDocumentContentCache] = useState<
    Map<number, string>
  >(new Map());
  const [editorRefreshTrigger, setEditorRefreshTrigger] = useState<number>(0);

  // Track which documents have been loaded to avoid unnecessary refreshes
  const loadedDocumentsRef = useRef<Set<number>>(new Set());

  const triggerEditorRefresh = useCallback(() => {
    setEditorRefreshTrigger((prev) => prev + 1);
  }, []);

  // Make the cache and triggerEditorRefresh globally available
  useEffect(() => {
    (window as any).documentContentCache = documentContentCache;
    (window as any).triggerEditorRefresh = triggerEditorRefresh;
    return () => {
      delete (window as any).documentContentCache;
      delete (window as any).triggerEditorRefresh;
    };
  }, [documentContentCache, triggerEditorRefresh]);

  // Fetch document content function
  const fetchDocumentContent = useCallback(
    async (docId: number, forceRefresh = false): Promise<string | null> => {
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

        // Check for undefined instead of truthy to properly handle empty strings
        if (cachedContent !== undefined) {
          logger.debug(
            `[CACHE_HIT ✅] Document ${docId}: Using cached content (${
              cachedContent?.length ?? 0
            } chars)`
          );
          // Mark document as loaded even when using cache
          loadedDocumentsRef.current.add(docId);

          // Update state for active document
          if (docId === activeDocumentId) {
            setDocumentContent(cachedContent);
            setContentLoadedSuccessfully(true);
            // Ensure loading is false when using cache for the active doc
            setIsLoadingContent(false);
          }

          return cachedContent;
        }
        logger.debug(
          `[CACHE_INVALID ⚠️] Document ${docId}: Cache entry exists but is undefined, fetching from database`
        );
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
        setFetchError(null);
        logger.debug(`[DB_FETCH 🔍] Document ${docId}: Fetching from database`);

        const response = await axiosInstance.get(`/api/documents/${docId}`);

        const documentData = response.data;
        const content = documentData.content || "";

        logger.debug(
          `[DB_FETCH ✅] Document ${docId}: Received ${content.length} chars from database`
        );

        // Mark this document as loaded after successful fetch
        loadedDocumentsRef.current.add(docId);

        // Always cache the content, even if it's empty
        logger.debug(
          `[CACHE_UPDATE 📝] Document ${docId}: Storing content in cache (${content.length} chars)`
        );
        setDocumentContentCache((prev) => {
          const newCache = new Map(prev);
          newCache.set(docId, content); // Always cache, even empty content
          logger.debug(
            `[CACHE_STATUS] Updated size: ${newCache.size} documents`
          );
          return newCache;
        });

        // Update state for active document
        if (docId === activeDocumentId) {
          setDocumentContent(content);
          setContentLoadedSuccessfully(true);
        }

        return content;
      } catch (err: any) {
        logger.error(`[DB_FETCH ❌] Document ${docId}: Failed to fetch:`, err);
        setFetchError(
          err.response?.data?.detail ||
            err.message ||
            "Error al cargar el contenido del documento"
        );
        return null;
      } finally {
        setIsLoadingContent(false);
      }
    },
    [documentContentCache, activeDocumentId]
  );

  // Wrapper for saving content that uses DocumentContext's saveDocument
  const saveContent = useCallback(
    async (docId: number, content: string): Promise<boolean> => {
      // Normalize line breaks and whitespace before comparing
      const normalizeBreaks = (text: string): string => {
        return text
          .replace(/\r\n/g, "\n")
          .replace(/\r/g, "\n")
          .replace(/\n\n+/g, "\n\n") // Collapse multiple newlines to max two
          .replace(/[ \t]+/g, " ") // Collapse multiple spaces
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
            `[DOC_SAVE] Document ${docId}: Content unchanged from cache, skipping save`
          );
          return true; // Return success without API call
        }

        // Save via DocumentContext
        const success = await saveDocument(docId, content);

        // Update cache after successful save
        if (success) {
          setDocumentContentCache((prev) => {
            const newCache = new Map(prev);
            newCache.set(docId, content);
            return newCache;
          });
        }

        return success;
      } catch (error) {
        logger.error("Error in saveContent:", error);
        return false;
      }
    },
    [documentContentCache, saveDocument]
  );

  // Reload content function
  const reloadContent = useCallback(
    async (forceRefresh: boolean = false): Promise<void> => {
      if (activeDocumentId) {
        logger.debug(
          `[RELOAD_CONTENT] Document ${activeDocumentId}, forceRefresh: ${forceRefresh}`
        );
        await fetchDocumentContent(activeDocumentId, forceRefresh);
      }
    },
    [activeDocumentId, fetchDocumentContent]
  );

  // Load content when active document changes
  useEffect(() => {
    if (activeDocumentId) {
      fetchDocumentContent(activeDocumentId);
    } else {
      setDocumentContent("");
      setContentLoadedSuccessfully(false);
    }
  }, [activeDocumentId, fetchDocumentContent]);

  // Clear cache when component unmounts
  useEffect(() => {
    return () => {
      logger.debug(`[CACHE_CLEAR 🧹] ContentContext unmounting, clearing cache`);
    };
  }, []);

  // Add new function to update document content directly (for real-time updates)
  const updateDocumentContent = useCallback(
    (docId: number, content: string) => {
      // Only update if it's the active document
      if (docId === activeDocumentId) {
        logger.debug(
          `[CONTENT_UPDATE] Directly updating content for document ${docId}`
        );
        setDocumentContent(content);
        setContentLoadedSuccessfully(true);
      }

      // Update the cache regardless
      setDocumentContentCache((prev) => {
        const newCache = new Map(prev);
        newCache.set(docId, content);
        return newCache;
      });
    },
    [activeDocumentId]
  );

  // Create the context value
  const value: ContentContextType = {
    documentContent,
    isLoadingContent,
    fetchError,
    contentLoadedSuccessfully,
    documentContentCache,
    editorRefreshTrigger,
    loadedDocumentIds: Array.from(loadedDocumentsRef.current),
    fetchDocumentContent,
    reloadContent,
    triggerEditorRefresh,
    saveContent,
    updateDocumentContent, // Include the new function
  };

  return (
    <ContentContext.Provider value={value}>{children}</ContentContext.Provider>
  );
}

// Custom hook
export function useContentContext() {
  const context = useContext(ContentContext);
  if (context === undefined) {
    throw new Error("useContentContext must be used within a ContentProvider");
  }
  return context;
}
