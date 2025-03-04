"use client";
import React, { useCallback } from "react";
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
import { useDocumentContent } from "../../../hooks/useDocumentContent";
import { createEditorConfig } from "./utils/editorConfig";

interface TextAreaProps {
  /**
   * Document to display/edit
   */
  document: DocumentoOut;

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
}

/**
 * TextArea component for editing and displaying medical documents
 * Uses Lexical editor for rich text editing capabilities
 */
const TextArea: React.FC<TextAreaProps> = ({
  document,
  readOnly = true,
  onSave,
  registerSaveFunction,
  documentContentCache,
  fetchDocumentContent,
  isLoadingContent = false,
}) => {
  // Use the document content hook to manage content loading
  const {
    documentContent,
    fetchError,
    isLoading: isContentLoading,
    contentLoadedSuccessfully,
  } = useDocumentContent({
    document,
    fetchDocumentContent,
    documentContentCache,
  });

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

  // Error handler for Lexical
  function onError(error: Error) {
    console.error("Lexical Editor error:", error);
  }

  // Create editor configuration
  const initialConfig = createEditorConfig(onError);

  // Determine if we should show the loading indicator
  const showLoading = isLoadingContent || isContentLoading;

  return (
    <div className="flex flex-col h-full">
      {/* Loading indicator - Fixed DIV closing tag */}
      {showLoading && (
        <div className="bg-gray-100 p-2 text-center text-gray-600 text-sm">
          Cargando contenido...
        </div>
      )}

      {/* Error display */}
      {fetchError && (
        <div className="bg-red-100 p-2 text-center text-red-600 text-sm">
          {fetchError}
        </div>
      )}

      {/* Editor container */}
      <div className="border rounded-md flex-1 bg-white">
        <LexicalComposer initialConfig={initialConfig}>
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
