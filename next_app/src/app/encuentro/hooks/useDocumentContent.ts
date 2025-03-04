import { useState, useEffect, useRef } from "react";
import { DocumentoOut } from "@/types/documento";

interface UseDocumentContentProps {
  document: DocumentoOut;
  fetchDocumentContent?: (
    docId: number,
    forceRefresh?: boolean
  ) => Promise<string | null>;
  documentContentCache?: Map<number, string>;
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
}: UseDocumentContentProps) => {
  const [documentContent, setDocumentContent] = useState<string | undefined>(
    undefined
  );
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const initialLoadRef = useRef<boolean>(true);
  const contentLoadedSuccessfully = useRef<boolean>(false);

  // Fetch document content when document changes
  useEffect(() => {
    async function loadDocumentContent() {
      setIsLoading(true);
      console.log(`Attempting to load content for document ID: ${document.id}`);

      // On initial page load or document change, always fetch fresh content
      const forceRefresh = initialLoadRef.current;

      // Try to fetch content using the provided function
      if (fetchDocumentContent) {
        try {
          console.log(
            `Fetching content for document ${document.id}, forceRefresh: ${forceRefresh}`
          );
          const content = await fetchDocumentContent(document.id, forceRefresh);

          if (content !== null) {
            console.log(
              `Received content for document ${
                document.id
              }: "${content.substring(0, 50)}..." (length: ${content.length})`
            );
            setDocumentContent(content);
            initialLoadRef.current = false;

            // Mark this document as successfully loaded if content exists
            if (content.trim().length > 0) {
              contentLoadedSuccessfully.current = true;
            }
            setIsLoading(false);
            return;
          }
        } catch (error) {
          console.error("Error fetching document content:", error);
          setFetchError("Error al cargar el contenido del documento");
        }
      }

      // Fallback to document.contenido if no fetch function
      if (!documentContent && document.contenido) {
        console.log(`Using fallback content for document ${document.id}`);
        setDocumentContent(document.contenido);

        if (document.contenido.trim().length > 0) {
          contentLoadedSuccessfully.current = true;
        }
      }

      initialLoadRef.current = false;
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
  ]);

  return {
    documentContent,
    fetchError,
    isLoading,
    contentLoadedSuccessfully: contentLoadedSuccessfully.current,
  };
};
