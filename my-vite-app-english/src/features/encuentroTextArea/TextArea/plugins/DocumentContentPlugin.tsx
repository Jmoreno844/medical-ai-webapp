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
  documentType,
}: DocumentContentPluginProps): React.ReactElement | null {
  const [editor] = useLexicalComposerContext();
  const lastAppliedContentRef = useRef<string | null>(null);
  const lastAppliedDocumentIdRef = useRef<number | null>(null);
  const isMountedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!isMountedRef.current || !editor) return;

    const isDocumentChanged = lastAppliedDocumentIdRef.current !== documentId;

    console.log(
      `📄 Plugin Effect Start: Doc ${documentId}, PrevDoc: ${
        lastAppliedDocumentIdRef.current
      }, isLoading: ${isLoading}, isDocChanged: ${isDocumentChanged}, contentLen: ${
        content?.length ?? "N/A"
      }, lastAppliedContentLen: ${
        lastAppliedContentRef.current?.length ?? "N/A"
      }`
    );

    editor.update(
      () => {
        if (!isMountedRef.current) return; // Re-check mount status inside closure

        const root = $getRoot();

        // --- Immediate Clear Logic ---
        // Clear the editor if the document ID has changed OR if loading has just started.
        // This prevents displaying stale content during the fetch.
        if (isDocumentChanged || isLoading) {
          // Only clear if we haven't already applied empty content for this loading state/doc change
          const currentEditorContent = root.getTextContent(); // Check actual editor state
          if (currentEditorContent !== "" || isDocumentChanged) {
            console.log(
              `📄 Clearing editor: Doc changed (${isDocumentChanged}), isLoading (${isLoading}). Current editor content length: ${currentEditorContent.length}`
            );
            root.clear();
            const paragraph = $createParagraphNode();
            root.append(paragraph);
            // Reset ref immediately after clearing due to load/change
            lastAppliedContentRef.current = "";
          } else {
            console.log(
              `📄 Skipping clear: Editor already empty for Doc ${documentId} while loading or doc changed.`
            );
          }
        }

        // --- Content Application Logic ---
        // Apply content only when *not* loading and the content is different from what's applied.
        // This runs *after* loading finishes or if it wasn't loading.
        if (!isLoading) {
          const newContent = streamingContent ?? content; // Prioritize streaming content if available

          if (newContent !== lastAppliedContentRef.current) {
            console.log(
              `📄 Applying content: Doc ${documentId}, isLoading: ${isLoading}, New content length: ${
                newContent?.length ?? 0
              }`
            );
            root.clear(); // Clear before applying new content
            if (newContent && newContent.trim() !== "") {
              try {
                // Use Markdown conversion for both regular and streaming for consistency
                $convertFromMarkdownString(newContent, TRANSFORMERS);
                console.log(
                  `📄 Applied content successfully for Doc ${documentId}`
                );
              } catch (error) {
                console.error(
                  `📄 Error converting Markdown for Doc ${documentId}:`,
                  error
                );
                // Fallback: insert as plain text paragraph
                const paragraph = $createParagraphNode();
                paragraph.append($createTextNode(newContent));
                root.append(paragraph);
              }
            } else {
              // Ensure empty content results in a single empty paragraph
              const paragraph = $createParagraphNode();
              root.append(paragraph);
              console.log(`📄 Applied empty paragraph for Doc ${documentId}`);
            }
            lastAppliedContentRef.current = newContent; // Update ref *after* successful application
          } else {
            console.log(
              `📄 Skipping content application: Content unchanged for Doc ${documentId}`
            );
          }
        } else {
          console.log(
            `📄 Skipping content application: Still loading Doc ${documentId}`
          );
        }
      },
      { tag: "document-content-plugin-update" }
    ); // Add tag for debugging Lexical updates

    // Update the document ID ref *after* the update logic has run
    if (isDocumentChanged) {
      lastAppliedDocumentIdRef.current = documentId;
    }
  }, [
    documentId,
    content,
    isLoading,
    streamingContent,
    editor,
    documentType,
    refreshTrigger,
  ]);

  return null;
}
