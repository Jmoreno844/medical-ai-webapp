import React, { useEffect, useRef } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { $getRoot, $createParagraphNode, $createTextNode } from "lexical";
import { $convertFromMarkdownString, TRANSFORMERS } from "@lexical/markdown";
import { useContentContext } from "@/contexts/ContentContext";

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
      // Skip if unchanged
      if (streamingContent === lastStreamContentRef.current) {
        return;
      }

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

        // For streaming content, we should not parse markdown
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
      (!content || content.length < lastStreamContentRef.current.length * 0.9) && // If content prop is significantly shorter than streamed
      !isLoading // And we are not currently loading new content
    ) {
      console.log(
        `⚠️ Document ${documentId}: Content prop (${
          content ? content.length : 0
        } chars) is shorter than last streamed content (${
          lastStreamContentRef.current.length
        } chars). Preserving streamed content temporarily.`
      );

      // Use the last streaming content we had
      const savedStreamContent = lastStreamContentRef.current;

      // REMOVE direct cache update - ContentContext should handle this
      // if (window.documentContentCache) {
      //   window.documentContentCache.set(documentId, savedStreamContent);
      //   console.log(
      //     `🛡️ Cache updated with preserved content (${savedStreamContent.length} chars)`
      //   );
      // }

      // Update editor with preserved content
      editor.update(() => {
        const root = $getRoot();
        root.clear();
        // Use markdown conversion here if the final content is expected to be markdown
        // If streaming content is plain text, use the previous logic
        $convertFromMarkdownString(savedStreamContent, TRANSFORMERS);
        // const lines = savedStreamContent.split("\n");
        // lines.forEach((line) => {
        //   const paragraph = $createParagraphNode();
        //   paragraph.append($createTextNode(line));
        //   root.append(paragraph);
        // });
      });

      // Set last updated ref to prevent immediate re-render with potentially empty 'content' prop
      lastUpdatedContentRef.current = savedStreamContent;

      // Clear the last stream ref now that we've used it as the primary content
      // This prevents this block from running again unless new streaming occurs
      lastStreamContentRef.current = "";

      return; // Prevent falling through to the regular content update logic immediately
    }
    // Handle the transition when streaming completes and content prop is updated
    else if (lastStreamContentRef.current && content && content.length > 0) {
        console.log(` transitioning from stream (${lastStreamContentRef.current.length}) to final content (${content.length})`);
        // Clear the stream ref as we are now using the final content prop
        lastStreamContentRef.current = "";
        // Allow the regular content update logic below to handle the final content
    }

    // Regular document content updates (non-streaming, or after streaming completes)
    if ((content && !isLoading) || forceRefresh) {
      // Skip if content is suspiciously short and we have better content
      // This check might be less necessary now but keep for safety
      // if (
      //   content.length <= 5 &&
      //   lastStreamContentRef.current && // Check removed as it's cleared above
      //   lastUpdatedContentRef.current.length > 100 // Compare with last known good content
      // ) {
      //   console.log(
      //     `⚠️ Rejecting suspicious short content update (${content.length} chars vs ${lastUpdatedContentRef.current.length} chars stored)`
      //   );
      //   return;
      // }

      // Check content length difference first
      const contentLengthChanged =
        lastUpdatedContentRef.current?.length !== content.length;

      // Skip if content is the same as last updated content AND not forced
      if (
        content === lastUpdatedContentRef.current &&
        !forceRefresh
      ) {
        // console.log( // Reduce noise
        //   `📄 Document ${documentId}: Content unchanged, skipping update`
        // );
        return;
      }

      // Add special handling for transcription documents to always update if content differs
      // if (isTranscription && lastUpdatedContentRef.current !== content) { // This might cause unnecessary updates if only whitespace changes
      //   console.log(
      //     `📝 Document ${documentId}: Transcription content update, forcing refresh`
      //   );
      // }

      console.log(
        `📄 Document ${documentId}: Applying regular content update (${content.length} chars)` +
          (contentLengthChanged ? " - Content length changed" : "") +
          (forceRefresh ? " - Force Refresh" : "")
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

        // Convert markdown to rich text
        $convertFromMarkdownString(content, TRANSFORMERS);
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
