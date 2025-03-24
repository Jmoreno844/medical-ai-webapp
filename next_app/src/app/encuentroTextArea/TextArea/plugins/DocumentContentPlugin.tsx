import React, { useEffect, useRef } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { $getRoot, $createParagraphNode, $createTextNode } from "lexical";

interface DocumentContentPluginProps {
    documentId: number;
    content: string;
    isLoading: boolean;
    refreshTrigger?: number;
    forceRefresh?: boolean;
    streamingContent?: string; // Add this new prop for streaming content
}

export function DocumentContentPlugin({
    documentId,
    content,
    isLoading,
    refreshTrigger,
    forceRefresh = false,
    streamingContent, // Support for streaming content
}: DocumentContentPluginProps): React.ReactElement | null {
    const [editor] = useLexicalComposerContext();
    const lastUpdatedContentRef = useRef<string>(""); // Track last content to avoid duplicate updates

    // Effect to update editor content when document changes or refresh triggers
    useEffect(() => {
        // Handle streaming content updates if provided and different from last update
        if (
            streamingContent !== undefined &&
            streamingContent !== lastUpdatedContentRef.current
        ) {
            console.log(
                `[EDITOR_PLUGIN] Updating editor with streaming content for document ${documentId} (${streamingContent.length} chars)`
            );

            lastUpdatedContentRef.current = streamingContent;

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

            return; // Skip the normal content update when streaming
        }

        // Regular document content updates (non-streaming)
        if ((content && !isLoading) || forceRefresh) {
            // Skip if content is the same as last updated content
            if (content === lastUpdatedContentRef.current && !forceRefresh) {
                return;
            }

            console.log(
                `[EDITOR_PLUGIN] Updating editor content for document ${documentId}${
                    forceRefresh ? " (forced)" : ""
                }`
            );

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
    ]);

    return null;
}
