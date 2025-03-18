import { useState, useEffect, useRef, useMemo } from "react";
import { DocumentoOut } from "@/types/documento";

interface UseDocumentContentProps {
    document: DocumentoOut;
    fetchDocumentContent?: (
        docId: number,
        forceRefresh?: boolean
    ) => Promise<string | null>;
    documentContentCache?: Map<number, string>;
    isDocumentLoaded?: boolean; // New prop to receive document loaded state
}

/**
 * Custom hook to manage document content loading and tracking
 *
 * @param props - Hook properties
 * @returns Content state and helper functions
 */
export const useDocumentContent = ({
    document,
    fetchDocumentContent,
    documentContentCache,
    isDocumentLoaded = false,
}: UseDocumentContentProps) => {
    const [documentContent, setDocumentContent] = useState<string | undefined>(
        undefined
    );
    const [fetchError, setFetchError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const contentLoadedSuccessfully = useRef<boolean>(false);
    const previousDocId = useRef<number | null>(null);
    const hasLoadedContentRef = useRef<boolean>(false);

    // Add stable reference tracking with useRef
    const documentIdRef = useRef<number | null>(null);

    // Track if we already loaded content from cache to prevent duplicate loads
    const alreadyLoadedFromCacheRef = useRef<Set<number>>(new Set());

    // Add state to track when content has been set
    const [contentHasBeenSet, setContentHasBeenSet] = useState(false);

    // Fetch document content when document changes
    useEffect(() => {
        // Skip if no document
        if (!document?.id) return;

        // Skip if content is already loaded for this exact document
        if (documentIdRef.current === document.id && contentHasBeenSet) {
            console.log(
                `[DOC_CONTENT] Document ${document.id}: Already loaded same document, skipping reload`
            );
            return;
        }

        // Update reference
        documentIdRef.current = document.id;

        async function loadDocumentContent() {
            setIsLoading(true);
            console.log(
                `[DOC_CONTENT] Document ${document.id}: Loading content`
            );

            // Get content from cache if available
            if (documentContentCache?.has(document.id)) {
                const cached = documentContentCache.get(document.id);
                if (cached && cached.trim().length > 0) {
                    console.log(
                        `[CACHE_USE ✅] Document ${document.id}: Using cached content directly`
                    );
                    setDocumentContent(cached);
                    setContentHasBeenSet(true);
                    contentLoadedSuccessfully.current = true;
                    setIsLoading(false);
                    return;
                }
            }

            // Otherwise fetch from server
            if (fetchDocumentContent) {
                setIsLoading(true);
                fetchDocumentContent(document.id, false)
                    .then((content) => {
                        if (content) {
                            setDocumentContent(content);
                            setContentHasBeenSet(true);
                            contentLoadedSuccessfully.current = true;
                        }
                    })
                    .catch((err) => {
                        setFetchError("Error loading document");
                    })
                    .finally(() => {
                        setIsLoading(false);
                    });
            }
        }

        loadDocumentContent();
    }, [document?.id, fetchDocumentContent, documentContentCache]);

    // Create a memoized version of documentContent to prevent unnecessary re-renders
    const memoizedDocumentContent = useMemo(() => {
        // If document content is already loaded, use that
        if (documentContent !== undefined) {
            return documentContent;
        }

        // Otherwise, check if we have it in cache
        if (document?.id && documentContentCache?.has(document.id)) {
            return documentContentCache.get(document.id) || "";
        }

        // Fall back to document's contenido property
        return document?.contenido || "";
    }, [
        document?.id,
        documentContent,
        documentContentCache,
        document?.contenido,
    ]);

    return {
        documentContent: memoizedDocumentContent,
        fetchError,
        isLoading,
        contentLoadedSuccessfully: contentLoadedSuccessfully.current,
    };
};
