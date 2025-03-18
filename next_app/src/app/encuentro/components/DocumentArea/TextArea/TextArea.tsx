"use client";
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
import { useDocumentContent } from "../../../hooks/useDocumentContent";
import { createEditorConfig } from "./utils/editorConfig";

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
    registerSaveFunction?: (
        saveFunc: (force?: boolean) => Promise<void>
    ) => void;

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
    onDocumentSwitch?: (
        oldDocId: number | null,
        newDocId: number | null
    ) => void;
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
}) => {
    // Track the previous document to detect changes
    const previousDocIdRef = useRef<number | null>(null);

    // Check if this document has been loaded before - moved up before potential early return
    const isDocumentLoaded = document
        ? loadedDocumentIds?.includes(document.id) || false
        : false;

    // Initialize content state - also moved above early return
    const {
        documentContent,
        fetchError,
        isLoading: isContentLoading,
        contentLoadedSuccessfully,
    } = useDocumentContent({
        document: document || ({} as DocumentoOut), // Provide fallback
        fetchDocumentContent,
        documentContentCache,
        isDocumentLoaded,
    });

    // Check if content is from cache for debugging - moved up before early return
    const isFromCache =
        (document && documentContentCache?.has(document.id)) || false;

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

    return (
        <div className="flex flex-col h-full">
            {/* Loading indicator */}
            {showLoading && (
                <div className="bg-gray-100 p-2 text-center text-gray-600 text-sm">
                    Cargando contenido...
                </div>
            )}

            {/* Cache status indicator (for debugging) */}
            {!showLoading && isFromCache && (
                <div className="bg-green-100 p-1 text-center text-green-600 text-xs flex justify-center items-center">
                    <span className="mr-1">🔄</span>
                    Contenido cargado desde caché (
                    {documentContentCache?.get(document.id)?.length || 0}{" "}
                    caracteres)
                </div>
            )}

            {/* Source indicator when content is from API/database */}
            {!showLoading && !isFromCache && documentContent && (
                <div className="bg-blue-100 p-1 text-center text-blue-600 text-xs flex justify-center items-center">
                    <span className="mr-1">🔍</span>
                    Contenido cargado desde base de datos (
                    {documentContent.length} caracteres)
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
                    key="persistent-editor"
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
                                    hasInitialContent={
                                        contentLoadedSuccessfully
                                    }
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
