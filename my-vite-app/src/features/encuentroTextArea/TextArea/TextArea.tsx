import React, { useCallback, useEffect, useRef, useState } from "react";
import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { RichTextPlugin } from "@lexical/react/LexicalRichTextPlugin";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { MarkdownShortcutPlugin } from "@lexical/react/LexicalMarkdownShortcutPlugin";
import { TRANSFORMERS } from "@lexical/markdown";

// Import custom plugins
import {
  AutoFocusPlugin,
  ReadOnlyPlugin,
  DocumentContentPlugin,
  AutoSavePlugin,
} from "./plugins";

// Import context hooks
import { useDocumentContext } from "../../../contexts/DocumentContext";
import { useContentContext } from "../../../contexts/ContentContext";
import { useGenerationContext } from "../../../contexts/GenerationContext";
import { useTranscriptionContext } from "../../../contexts/TranscriptionContext";

// Import utilities
import { createEditorConfig } from "./utils/editorConfig";

const TextArea: React.FC = () => {
  // Get state from contexts instead of props
  const { activeDocument, activeDocumentId } = useDocumentContext();

  const {
    documentContent,
    fetchError,
    isLoadingContent,
    contentLoadedSuccessfully,
    reloadContent,
    saveContent,
    editorRefreshTrigger,
    documentContentCache, // Add this line
  } = useContentContext();

  const { generationStatus } = useGenerationContext();
  const { transcriptionCompleteTimestamp } = useTranscriptionContext();

  // Local state & refs
  const [showGenerationSuccess, setShowGenerationSuccess] = useState(false);
  const previousDocIdRef = useRef(null);
  const previousRefreshTriggerRef = useRef(editorRefreshTrigger);

  // Update refresh trigger when needed
  useEffect(() => {
    if (
      activeDocument &&
      editorRefreshTrigger !== previousRefreshTriggerRef.current
    ) {
      console.log(
        `[TEXT_AREA] Refresh trigger changed to ${editorRefreshTrigger} for document ${activeDocument.id}`
      );
      previousRefreshTriggerRef.current = editorRefreshTrigger;

      // Check if the document is already in the cache
      if (documentContentCache.has(activeDocument.id)) {
        console.log(
          `[TEXT_AREA] Document ${activeDocument.id} already in cache, skipping reloadContent`
        );
        return; // Skip reloadContent if already cached
      }

      if (typeof reloadContent === "function") {
        console.log(
          `[TEXT_AREA] Calling reloadContent for document ${activeDocument.id}`
        );
        const forceRefresh = false;
        reloadContent(forceRefresh);
      }
    }
  }, [
    editorRefreshTrigger,
    activeDocument,
    reloadContent,
    documentContentCache,
  ]);

  // Enhanced logic to track transcription updates
  useEffect(() => {
    if (
      transcriptionCompleteTimestamp &&
      activeDocument?.tipo === "transcripcion" &&
      activeDocument.id === previousDocIdRef.current
    ) {
      console.log(
        `[TEXT_AREA] Transcription completed at ${new Date(
          transcriptionCompleteTimestamp
        ).toISOString()}`
      );
      // Force refresh for transcription updates since we need the latest content
      reloadContent(true);
    }
  }, [transcriptionCompleteTimestamp, activeDocument, reloadContent]);

  // Custom save wrapper
  const handleSave = useCallback(
    async (docId: number, content: string) => {
      // Prevent saving empty content for documents that previously had content
      if (contentLoadedSuccessfully && content.trim() === "") {
        console.error(
          "Prevented saving empty content for a document that previously had content"
        );
        return;
      }

      await saveContent(docId, content);
    },
    [saveContent, contentLoadedSuccessfully]
  );

  // Track document changes
  useEffect(() => {
    if (!activeDocument) return;

    if (activeDocument.id !== previousDocIdRef.current) {
      console.log(
        `[DOC_SWITCH] Changed from document ${previousDocIdRef.current} to ${activeDocument.id}`
      );
      previousDocIdRef.current = activeDocument.id;
    }
  }, [activeDocument?.id]);

  // Show generation success indicator
  useEffect(() => {
    if (
      generationStatus?.isComplete &&
      activeDocument &&
      generationStatus.documentId === activeDocument.id
    ) {
      setShowGenerationSuccess(true);
      const timer = setTimeout(() => {
        setShowGenerationSuccess(false);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [generationStatus, activeDocument]);

  // Early return if no document
  if (!activeDocument) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-xl font-medium">
        Select a document
      </div>
    );
  }

  // Error handler for Lexical
  function onError(error: Error) {
    console.error("Lexical Editor error:", error);
  }

  // Create editor configuration
  const initialConfig = createEditorConfig(onError);

  // Check if content is being streamed for this document
  const streamingContent =
    activeDocument &&
    generationStatus?.documentId === activeDocument.id &&
    generationStatus.inProgress
      ? generationStatus.content
      : undefined;

  return (
    <div className="flex flex-col h-full">
      {/* Loading indicator */}
      {isLoadingContent && (
        <div className="bg-gray-100 p-2 text-center text-gray-600 text-sm">
          Loading content...
        </div>
      )}

      {/* Streaming indicator */}
      {streamingContent !== undefined && (
        <div className="bg-purple-100 p-2 border-b border-purple-200">
          <div className="flex items-center justify-between">
            <div className="w-24 invisible"></div>
            <div className="flex items-center">
              <div className="animate-pulse h-3 w-3 rounded-full bg-purple-500 mr-2"></div>
              <span className="text-purple-800 font-medium">
                Generating document...
              </span>
            </div>
            <div className="text-purple-600 text-sm w-24 text-right">
              {streamingContent.length} characters
            </div>
          </div>

          {generationStatus?.error && (
            <div className="mt-2 p-2 bg-red-100 text-red-700 rounded text-sm">
              <strong>Error:</strong> {generationStatus.error}
            </div>
          )}
        </div>
      )}

      {/* Progress bar */}
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

      {/* Generation success indicator */}
      {showGenerationSuccess && (
        <div className="bg-green-100 p-2 border-b border-green-200 text-green-800">
          <div className="flex items-center justify-center">
            <svg
              className="h-4 w-4 mr-2"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            <span className="font-medium">Document generated successfully</span>
          </div>
        </div>
      )}

      {/* Error display */}
      {fetchError && (
        <div className="bg-red-100 p-2 text-center text-red-600 text-sm">
          {fetchError}
        </div>
      )}

      {/* Editor */}
      <div className="border rounded-md flex-1 bg-white">
        <LexicalComposer
          key={`editor-${activeDocumentId}-refresh-${editorRefreshTrigger}`}
          initialConfig={initialConfig}
        >
          <div className="editor-container h-full">
            <RichTextPlugin
              contentEditable={
                <ContentEditable className="h-full px-4 py-3 focus:outline-none overflow-auto" />
              }
              placeholder={
                <div className="text-gray-400 absolute top-3 left-4 pointer-events-none">
                  {activeDocument.tipo === "transcripcion"
                    ? ""
                    : "Start typing..."}
                </div>
              }
              ErrorBoundary={LexicalErrorBoundary}
            />

            {/* Core plugins */}
            <HistoryPlugin />
            <MarkdownShortcutPlugin transformers={TRANSFORMERS} />
            <DocumentContentPlugin
              documentId={activeDocument.id}
              content={documentContent}
              isLoading={isLoadingContent}
              refreshTrigger={editorRefreshTrigger}
              forceRefresh={false}
              streamingContent={streamingContent}
              documentType={activeDocument.tipo}
            />
            <ReadOnlyPlugin
              isReadOnly={activeDocument.tipo === "transcripcion"}
            />

            {/* Conditional plugins for edit mode */}
            {activeDocument.tipo !== "transcripcion" && (
              <>
                <AutoFocusPlugin />
                <AutoSavePlugin
                  onSave={handleSave}
                  documentId={activeDocument.id}
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
