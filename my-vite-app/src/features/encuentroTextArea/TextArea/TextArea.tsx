import React, { useCallback, useEffect, useRef, useState } from "react";
import { DocumentoOut } from "@/types/documento";
import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { RichTextPlugin } from "@lexical/react/LexicalRichTextPlugin";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";

// Import custom plugins
import {
  AutoFocusPlugin,
  ReadOnlyPlugin,
  DocumentContentPlugin,
  AutoSavePlugin,
} from "./plugins";

// Import custom hooks and utilities
import { useDocumentContent } from "../../encuentro/hooks/useDocumentContent";
import { createEditorConfig } from "./utils/editorConfig";

// Create a global cache reference for direct access
declare global {
  interface Window {
    documentContentCache: Map<number, string> | undefined;
  }
}

interface TextAreaProps {
  /**
   * Current document to display/edit
   */
  document: DocumentoOut | null;

  /**
   * All available documents
   */
  allDocuments: DocumentoOut[];

  /**
   * Active document ID
   */
  activeDocumentId: number | null;

  /**
   * Whether the editor is in read-only mode
   */
  readOnly?: boolean;

  /**
   * Function to save document content
   */
  onSave?: (documentId: number, content: string) => Promise<void>;

  /**
   * Function to register the save function with the parent component
   */
  registerSaveFunction?: (saveFunc: (force?: boolean) => Promise<void>) => void;

  /**
   * Cache of document content
   */
  documentContentCache?: Map<number, string>;

  /**
   * Function to fetch document content
   */
  fetchDocumentContent?: (docId: number) => Promise<string | null>;

  /**
   * Whether document content is currently loading
   */
  isLoadingContent?: boolean;

  /**
   * List of document IDs that have already been loaded
   */
  loadedDocumentIds?: number[];

  /**
   * Callback when document switches
   */
  onDocumentSwitch?: (oldDocId: number | null, newDocId: number | null) => void;

  /**
   * Force refresh trigger - increment to force the editor to reload content
   */
  refreshTrigger?: number;

  generationStatus?: {
    inProgress: boolean;
    documentId: number | null;
    content: string;
    error: string | null;
    isComplete: boolean;
  };
}

/**
 * TextArea component for editing and displaying medical documents
 * Uses Lexical editor for rich text editing capabilities
 */
const TextArea: React.FC<TextAreaProps> = ({
  document,
  allDocuments,
  activeDocumentId,
  readOnly = true,
  onSave,
  registerSaveFunction,
  documentContentCache,
  fetchDocumentContent,
  isLoadingContent = false,
  loadedDocumentIds = [],
  onDocumentSwitch,
  refreshTrigger = 0,
  generationStatus,
}) => {
  // Track the previous document to detect changes
  const previousDocIdRef = useRef<number | null>(null);

  // Track the refresh trigger to detect external content updates
  const previousRefreshTriggerRef = useRef(refreshTrigger);

  // Check if this document has been loaded before - moved up before potential early return
  const isDocumentLoaded = document
    ? loadedDocumentIds?.includes(document.id) || false
    : false;

  // Make the cache globally available for direct updates
  useEffect(() => {
    // Make the cache globally available for direct updates
    if (documentContentCache) {
      window.documentContentCache = documentContentCache;
    }

    return () => {
      // Clean up on unmount
      delete window.documentContentCache;
    };
  }, [documentContentCache]);

  // Initialize content state - also moved above early return
  const {
    documentContent,
    fetchError,
    isLoading: isContentLoading,
    contentLoadedSuccessfully,
    reloadContent, // Add this method to useDocumentContent hook or implement inline
  } = useDocumentContent({
    document: document || ({} as DocumentoOut), // Provide fallback
    fetchDocumentContent,
    documentContentCache,
    isDocumentLoaded,
  });

  // Detect external content updates via refreshTrigger
  useEffect(() => {
    if (document && refreshTrigger !== previousRefreshTriggerRef.current) {
      console.log(
        `[TEXT_AREA] Refresh trigger changed from ${previousRefreshTriggerRef.current} to ${refreshTrigger} for document ${document.id}`
      );
      previousRefreshTriggerRef.current = refreshTrigger;
      if (typeof reloadContent === "function") {
        console.log(
          `[TEXT_AREA] Calling reloadContent for document ${document.id}`
        );
        reloadContent();
      }
    }
  }, [refreshTrigger, document, documentContentCache, reloadContent]);

  // Define all hooks before conditional logic
  // Custom save wrapper to prevent saving empty content for documents that had content
  const handleSave = useCallback(
    async (docId: number, content: string) => {
      // Check if we're trying to save empty content for a document that previously had content
      if (contentLoadedSuccessfully && content.trim() === "") {
        console.error(
          "Prevented saving empty content for a document that previously had content"
        );
        return;
      }

      // Proceed with normal save
      if (onSave) {
        await onSave(docId, content);
      }
    },
    [onSave, contentLoadedSuccessfully]
  );

  // Replace the current document switching effect with an optimized version
  useEffect(() => {
    // Only run if we have a document
    if (!document) return;

    // Create stable function to avoid depending on onDocumentSwitch
    function notifyDocumentSwitch() {
      if (onDocumentSwitch && document.id !== previousDocIdRef.current) {
        onDocumentSwitch(previousDocIdRef.current, document.id);
        previousDocIdRef.current = document.id;
      }
    }

    // Run once per document change
    notifyDocumentSwitch();

    // No cleanup needed, we're just tracking changes
  }, [document?.id]); // Only depend on document.id, not the entire document object

  // Monitor generationStatus and manually update the cache
  useEffect(() => {
    if (!generationStatus || !documentContentCache) return;

    // When streaming content changes, update our cache to ensure it's always current
    if (
      generationStatus.inProgress &&
      generationStatus.documentId &&
      generationStatus.content
    ) {
      const docId = generationStatus.documentId;
      const content = generationStatus.content;

      // Keep the cache updated with streaming content
      if (content.length > 5) {
        // Only update if we have meaningful content
        console.log(
          `🔄 Syncing streaming content to cache (${content.length} chars)`
        );
        documentContentCache.set(docId, content);
      }
    }
  }, [
    generationStatus?.content,
    generationStatus?.documentId,
    documentContentCache,
  ]);

  // Log component lifecycle for debugging
  useEffect(() => {
    if (document) {
      console.log(`[TEXT_AREA] Document ${document.id}: Content updated`);
    }
  }, [document, documentContent]);

  // Log cache status for debugging
  useEffect(() => {
    if (document && documentContentCache?.has(document.id)) {
      console.log(
        `[CACHE_DATA] Document ${document.id}: Cached content available`
      );
    }
  }, [document, documentContentCache]);

  // Only proceed with rendering editor if we have a document
  if (!document) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        Seleccione un documento para visualizar
      </div>
    );
  }

  // Error handler for Lexical
  function onError(error: Error) {
    console.error("Lexical Editor error:", error);
  }

  // Create editor configuration
  const initialConfig = createEditorConfig(onError);

  // Determine if we should show the loading indicator
  const showLoading = isLoadingContent || isContentLoading;

  // Check if content is from cache for debugging
  const isFromCache =
    (document && documentContentCache?.has(document.id)) || false;

  // Extract streaming content when this is the active generated document
  const streamingContent =
    document &&
    generationStatus?.documentId === document.id &&
    generationStatus.inProgress
      ? generationStatus.content
      : undefined;

  return (
    <div className="flex flex-col h-full">
      {/* Loading indicator */}
      {showLoading && (
        <div className="bg-gray-100 p-2 text-center text-gray-600 text-sm">
          Cargando contenido...
        </div>
      )}

      {/* Enhanced streaming indicator when content is being streamed */}
      {streamingContent !== undefined && (
        <div className="bg-purple-100 p-2 border-b border-purple-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="animate-pulse h-3 w-3 rounded-full bg-purple-500 mr-2"></div>
              <span className="text-purple-800 font-medium">
                Generando documento...
              </span>
            </div>
            <div className="text-purple-600 text-sm">
              {streamingContent.length} caracteres
            </div>
          </div>

          {generationStatus?.error && (
            <div className="mt-2 p-2 bg-red-100 text-red-700 rounded text-sm">
              <strong>Error:</strong> {generationStatus.error}
            </div>
          )}
        </div>
      )}

      {/* Add a progress bar for better visual feedback */}
      {streamingContent !== undefined && (
        <div className="h-1 w-full bg-purple-200">
          <div
            className="h-1 bg-purple-600 transition-all duration-300"
            style={{
              width: `${Math.min(
                Math.max((streamingContent.length / 500) * 100, 10),
                95
              )}%`,
            }}
          />
        </div>
      )}

      {/* Add completion indicator when generation is complete */}
      {!streamingContent &&
        generationStatus?.isComplete &&
        generationStatus?.documentId === document.id && (
          <div className="bg-green-100 p-2 border-b border-green-200 text-green-800">
            <div className="flex items-center">
              <svg
                className="h-4 w-4 mr-2"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M16.707 5.293a1 1 0 010 1.414l-8 8a 1 1 0 01-1.414 0l-4-4a 1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="font-medium">
                Documento generado exitosamente
              </span>
            </div>
          </div>
        )}

      {/* Cache status indicator (for debugging) */}
      {!showLoading && isFromCache && (
        <div className="bg-green-100 p-1 text-center text-green-600 text-xs flex justify-center items-center">
          <span className="mr-1">🔄</span>
          Contenido cargado desde caché (
          {documentContentCache?.get(document.id)?.length || 0} caracteres)
        </div>
      )}

      {/* Source indicator when content is from API/database */}
      {!showLoading && !isFromCache && documentContent && (
        <div className="bg-blue-100 p-1 text-center text-blue-600 text-xs flex justify-center items-center">
          <span className="mr-1">🔍</span>
          Contenido cargado desde base de datos ({documentContent.length}{" "}
          caracteres)
        </div>
      )}

      {/* Error display */}
      {fetchError && (
        <div className="bg-red-100 p-2 text-center text-red-600 text-sm">
          {fetchError}
        </div>
      )}

      {/* Use a persistent editor without document ID in the key */}
      <div className="border rounded-md flex-1 bg-white">
        <LexicalComposer
          key={`persistent-editor-${refreshTrigger}`} // Add refreshTrigger to key to force remount when needed
          initialConfig={initialConfig}
        >
          <div className="editor-container h-full">
            <RichTextPlugin
              contentEditable={
                <ContentEditable className="h-full px-4 py-3 focus:outline-none overflow-auto" />
              }
              placeholder={
                <div className="text-gray-400 absolute top-3 left-4 pointer-events-none">
                  {readOnly ? "" : "Comience a escribir..."}
                </div>
              }
              ErrorBoundary={LexicalErrorBoundary}
            />

            {/* Core plugins */}
            <HistoryPlugin />
            <DocumentContentPlugin
              documentId={document.id}
              content={documentContent}
              isLoading={showLoading}
              refreshTrigger={refreshTrigger} // Pass refresh trigger to plugin
              forceRefresh={false} // Remove the force refresh, use streaming instead
              streamingContent={streamingContent} // Pass streaming content here
              documentType={document.tipo} // Pass document type
            />
            <ReadOnlyPlugin isReadOnly={readOnly} />

            {/* Conditional plugins for edit mode */}
            {!readOnly && (
              <>
                <AutoFocusPlugin />
                <AutoSavePlugin
                  onSave={handleSave}
                  documentId={document.id}
                  registerSaveFunction={registerSaveFunction}
                  hasInitialContent={contentLoadedSuccessfully}
                />
              </>
            )}
          </div>
        </LexicalComposer>
      </div>
    </div>
  );
};

export default TextArea;
