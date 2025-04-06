import React, { useEffect, useRef } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { $getRoot, $createParagraphNode, $createTextNode } from "lexical";

interface DocumentContentPluginProps {
  documentId: number;
  content: string;
  isLoading: boolean;
  refreshTrigger?: number;
  forceRefresh?: boolean;
  streamingContent?: string;
  documentType?: string; // Add document type to determine refresh behavior
}

export function DocumentContentPlugin({
  documentId,
  content,
  isLoading,
  refreshTrigger,
  forceRefresh = false,
  streamingContent,
  documentType, // Read document type
}: DocumentContentPluginProps): React.ReactElement | null {
  const [editor] = useLexicalComposerContext();
  const lastUpdatedContentRef = useRef<string>("");
  const lastStreamContentRef = useRef<string>("");
  const isTranscription = documentType === "transcripcion"; // Check if this is a transcription document

  // Effect to update editor content when document changes or refresh triggers
  useEffect(() => {
    // Debug logging to track content transitions
    if (streamingContent) {
      console.log(
        `🔄 Document ${documentId}: Using streaming content (${streamingContent.length} chars)`
      );
      lastStreamContentRef.current = streamingContent;
    } else if (content) {
      console.log(
        `📄 Document ${documentId}: Using regular content (${content.length} chars)`
      );
    } else if (lastStreamContentRef.current) {
      console.log(
        `🔍 Document ${documentId}: Fallback to last stream content (${lastStreamContentRef.current.length} chars)`
      );
    }

    // Handle streaming content updates if provided
    if (streamingContent && streamingContent.length > 5) {
      // Only use if substantial content
      console.log(
        `🔄 Document ${documentId}: Using streaming content (${streamingContent.length} chars)`
      );

      lastStreamContentRef.current = streamingContent;

      editor.update(() => {
        // Clear editor
        const root = $getRoot();
        root.clear();

        // If no content, just add an empty paragraph
        if (!streamingContent) {
          const paragraph = $createParagraphNode();
          root.append(paragraph);
          return;
        }

        // Simple content parsing: split by new lines
        const lines = streamingContent.split("\n");

        lines.forEach((line) => {
          const paragraph = $createParagraphNode();
          paragraph.append($createTextNode(line));
          root.append(paragraph);
        });
      });

      // Important: Save the streaming content as the last updated content
      lastUpdatedContentRef.current = streamingContent;
      return;
    }
    // ENHANCED: Better detection of content truncation after streaming ends
    else if (
      lastStreamContentRef.current &&
      (!content || content.length < lastStreamContentRef.current.length * 0.9) // If content is less than 90% of streamed content
    ) {
      console.log(
        `⚠️ Document ${documentId}: Content truncation detected (${
          content ? content.length : 0
        } chars vs ${
          lastStreamContentRef.current.length
        } chars streamed). Preserving full content.`
      );

      // Use the last streaming content we had
      const savedStreamContent = lastStreamContentRef.current;

      // Update the global cache to ensure consistency
      if (window.documentContentCache) {
        window.documentContentCache.set(documentId, savedStreamContent);
        console.log(
          `🛡️ Cache updated with preserved content (${savedStreamContent.length} chars)`
        );
      }

      editor.update(() => {
        const root = $getRoot();
        root.clear();

        const lines = savedStreamContent.split("\n");
        lines.forEach((line) => {
          const paragraph = $createParagraphNode();
          paragraph.append($createTextNode(line));
          root.append(paragraph);
        });
      });

      return;
    }
    // Handle the transition when streaming completes
    else if (
      lastStreamContentRef.current &&
      (!content || content.length <= 1)
    ) {
      console.log(
        `⚠️ Document ${documentId}: Content appears empty/truncated. Using last stream content (${lastStreamContentRef.current.length} chars).`
      );

      // Use the last streaming content we had
      const savedStreamContent = lastStreamContentRef.current;

      editor.update(() => {
        const root = $getRoot();
        root.clear();

        const lines = savedStreamContent.split("\n");
        lines.forEach((line) => {
          const paragraph = $createParagraphNode();
          paragraph.append($createTextNode(line));
          root.append(paragraph);
        });
      });

      return;
    }

    // Regular document content updates (non-streaming)
    if ((content && !isLoading) || forceRefresh) {
      // Skip if content is suspiciously short and we have better content
      if (
        content.length <= 5 &&
        lastStreamContentRef.current &&
        lastStreamContentRef.current.length > 100
      ) {
        console.log(
          `⚠️ Rejecting suspicious short content update (${content.length} chars vs ${lastStreamContentRef.current.length} chars stored)`
        );
        return;
      }

      // Check content length difference first - if lengths differ, content has changed
      // This is critical for transcription documents
      const contentLengthChanged =
        lastUpdatedContentRef.current?.length !== content.length;

      // Skip if content is the same as last updated content
      if (
        content === lastUpdatedContentRef.current &&
        !contentLengthChanged &&
        !forceRefresh
      ) {
        console.log(
          `📄 Document ${documentId}: Content unchanged, skipping update`
        );
        return;
      }

      // Add special handling for transcription documents to always update
      if (isTranscription && lastUpdatedContentRef.current !== content) {
        console.log(
          `📝 Document ${documentId}: Transcription content update, forcing refresh`
        );
        // Force update for transcriptions, don't return early
      }

      console.log(
        `📄 Document ${documentId}: Using regular content (${content.length} chars)` +
          (contentLengthChanged ? " - Content length changed" : "")
      );

      // Always update lastUpdatedContentRef before applying changes
      lastUpdatedContentRef.current = content;

      editor.update(() => {
        // Clear editor
        const root = $getRoot();
        root.clear();

        // If no content, just add an empty paragraph
        if (!content) {
          const paragraph = $createParagraphNode();
          root.append(paragraph);
          return;
        }

        // Simple content parsing: split by new lines
        const lines = content.split("\n");

        lines.forEach((line) => {
          const paragraph = $createParagraphNode();
          paragraph.append($createTextNode(line));
          root.append(paragraph);
        });
      });
    }
  }, [
    documentId,
    content,
    isLoading,
    refreshTrigger,
    forceRefresh,
    editor,
    streamingContent,
    documentType, // Add documentType to dependencies
  ]);

  return null;
}
