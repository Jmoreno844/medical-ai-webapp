import { useState, useEffect, useRef } from "react";
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

    // Fetch document content when document changes
    useEffect(() => {
        async function loadDocumentContent() {
            setIsLoading(true);
            console.log(
                `[DOC_CONTENT] Document ${document.id}: Loading content`
            );

            // Determine if this is a document change
            const isDocumentChange =
                previousDocId.current !== null &&
                previousDocId.current !== document.id;
            previousDocId.current = document.id;

            // Only force refresh if this document hasn't been loaded before
            // Use the isDocumentLoaded prop which comes from the parent component's tracking
            const shouldForceRefresh = !isDocumentLoaded;

            console.log(
                `[DOC_LOAD_STATUS] Document ${document.id}: Already loaded: ${isDocumentLoaded}, Document change: ${isDocumentChange}`
            );

            // Log cache status
            if (documentContentCache) {
                console.log(
                    `[CACHE_STATUS] Size: ${documentContentCache.size} documents`
                );
                if (documentContentCache.has(document.id)) {
                    const cachedContent =
                        documentContentCache.get(document.id) || "";
                    console.log(
                        `[CACHE_CHECK ✅] Document ${document.id}: Found in cache (${cachedContent.length} chars)`
                    );

                    // If we have valid cache, use it directly unless we need to force refresh
                    if (
                        !shouldForceRefresh &&
                        cachedContent.trim().length > 0
                    ) {
                        console.log(
                            `[CACHE_USE ✅] Document ${document.id}: Using cached content directly`
                        );
                        setDocumentContent(cachedContent);
                        contentLoadedSuccessfully.current = true;
                        setIsLoading(false);
                        return;
                    }
                } else {
                    console.log(
                        `[CACHE_CHECK ❌] Document ${document.id}: Not in cache`
                    );
                }
            }

            // Log force refresh status
            if (shouldForceRefresh) {
                console.log(
                    `[DOC_CONTENT] Document ${document.id}: First load for this document, forcing refresh`
                );
            }

            // Try to fetch content using the provided function
            if (fetchDocumentContent) {
                try {
                    console.log(
                        `[DOC_FETCH] Document ${document.id}: Requesting content, forceRefresh: ${shouldForceRefresh}`
                    );
                    const content = await fetchDocumentContent(
                        document.id,
                        shouldForceRefresh
                    );

                    if (content !== null) {
                        const contentPreview =
                            content.length > 50
                                ? content.substring(0, 50) + "..."
                                : content;

                        console.log(
                            `[DOC_FETCH ✅] Document ${document.id}: Received "${contentPreview}" (${content.length} chars)`
                        );
                        setDocumentContent(content);

                        // Mark this document as loaded
                        loadedDocumentsRef.current.add(document.id);

                        // Mark this document as successfully loaded if content exists
                        if (content.trim().length > 0) {
                            contentLoadedSuccessfully.current = true;
                            console.log(
                                `[DOC_CONTENT ✅] Document ${document.id}: Content loaded successfully`
                            );
                        } else {
                            console.log(
                                `[DOC_CONTENT ⚠️] Document ${document.id}: Empty content received`
                            );
                        }
                        setIsLoading(false);
                        return;
                    }
                } catch (error) {
                    console.error(
                        "[DOC_FETCH ❌] Error fetching document content:",
                        error
                    );
                    setFetchError("Error al cargar el contenido del documento");
                }
            }

            // Fallback to document.contenido if no fetch function
            if (!documentContent && document.contenido) {
                console.log(
                    `[DOC_CONTENT ℹ️] Document ${document.id}: Using fallback content from document object`
                );
                setDocumentContent(document.contenido);

                if (document.contenido.trim().length > 0) {
                    contentLoadedSuccessfully.current = true;
                    // Mark this document as loaded
                    loadedDocumentsRef.current.add(document.id);
                }
            }

            setIsLoading(false);
        }

        loadDocumentContent();

        // Cleanup function
        return () => {
            // Reset loading state when component unmounts or document changes
            setIsLoading(false);
        };
    }, [
        document.id,
        document.contenido,
        fetchDocumentContent,
        documentContentCache,
        isDocumentLoaded, // Add this prop to the dependencies
    ]);

    return {
        documentContent,
        fetchError,
        isLoading,
        contentLoadedSuccessfully: contentLoadedSuccessfully.current,
    };
};
