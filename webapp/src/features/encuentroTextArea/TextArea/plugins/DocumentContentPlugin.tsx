import React, { useEffect, useRef } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { $getRoot, $createParagraphNode, $createTextNode } from "lexical";
import { $convertFromMarkdownString, TRANSFORMERS } from "@lexical/markdown";

import { logger } from "@/lib/logger";
interface DocumentContentPluginProps {
  documentId: number;
  content: string;
  isLoading: boolean;
  refreshTrigger?: number;
  forceRefresh?: boolean;
  streamingContent?: string;
  documentType?: string;
}

export function DocumentContentPlugin({
  documentId,
  content,
  isLoading,
  refreshTrigger,
  forceRefresh: _forceRefresh = false,
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

    editor.update(
      () => {
        if (!isMountedRef.current) return;

        const root = $getRoot();

        // Clear editor when document changes or loading starts
        if (isDocumentChanged || isLoading) {
          const currentEditorContent = root.getTextContent();
          if (currentEditorContent !== "" || isDocumentChanged) {
            logger.debug(
              `📄 Clearing editor: Doc changed (${isDocumentChanged}), isLoading (${isLoading})`
            );
            root.clear();
            const paragraph = $createParagraphNode();
            root.append(paragraph);
            lastAppliedContentRef.current = "";
          }
        }

        // Apply content when not loading
        if (!isLoading) {
          const newContent = streamingContent ?? content;

          if (newContent !== lastAppliedContentRef.current) {
            logger.debug(
              `📄 Applying content: Doc ${documentId}, content length: ${
                newContent?.length ?? 0
              }`
            );
            
            root.clear();
            
            if (newContent && newContent.trim() !== "") {
              try {
                $convertFromMarkdownString(newContent, TRANSFORMERS);
              } catch (error) {
                logger.error(`Error converting Markdown for Doc ${documentId}:`, error);
                const paragraph = $createParagraphNode();
                paragraph.append($createTextNode(newContent));
                root.append(paragraph);
              }
            } else {
              const paragraph = $createParagraphNode();
              root.append(paragraph);
            }
            
            lastAppliedContentRef.current = newContent;
          }
        }
      },
      { tag: "document-content-plugin-update" }
    );

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
