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
}

export function DocumentContentPlugin({
    documentId,
    content,
    isLoading,
    refreshTrigger,
    forceRefresh = false,
    streamingContent,
}: DocumentContentPluginProps): React.ReactElement | null {
    const [editor] = useLexicalComposerContext();
    const lastUpdatedContentRef = useRef<string>("");
    const lastStreamContentRef = useRef<string>("");

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

            // Skip if content is the same as last updated content
            if (content === lastUpdatedContentRef.current && !forceRefresh) {
                return;
            }

            console.log(
                `📄 Document ${documentId}: Using regular content (${content.length} chars)`
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
