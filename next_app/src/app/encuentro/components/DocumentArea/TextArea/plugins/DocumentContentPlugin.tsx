import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { useEffect, useRef, useCallback } from "react";
import { $getRoot, $createParagraphNode, $createTextNode } from "lexical";

interface DocumentContentPluginProps {
    documentId: number;
    content?: string;
    isLoading?: boolean;
}

export function DocumentContentPlugin({
    documentId,
    content,
    isLoading = false,
}: DocumentContentPluginProps) {
    const [editor] = useLexicalComposerContext();
    const contentRef = useRef(content);
    const docIdRef = useRef(documentId);

    // Function to get current editor content
    const getCurrentEditorContent = useCallback(() => {
        let editorContent = "";
        editor.read(() => {
            const root = $getRoot();
            editorContent = root.getTextContent();
        });
        return editorContent;
    }, [editor]);

    useEffect(() => {
        // Skip if loading or no content
        if (isLoading || content === undefined) return;

        const documentChanged = documentId !== docIdRef.current;

        // Check if content has actually changed
        const currentEditorContent = getCurrentEditorContent();
        const incomingContentDiffersFromEditor =
            content.trim() !== currentEditorContent.trim();
        const incomingContentDiffersFromRef = content !== contentRef.current;

        // Only update when necessary
        if (
            !documentChanged &&
            !incomingContentDiffersFromEditor &&
            !incomingContentDiffersFromRef
        ) {
            console.log(
                `[EDITOR_CONTENT] Document ${documentId}: Content unchanged, skipping update`
            );
            return;
        }

        // Log the update reason
        console.log(
            `[EDITOR_CONTENT] Updating document ${documentId} content:` +
                (documentChanged ? " (document changed)" : "") +
                (incomingContentDiffersFromEditor
                    ? " (content differs from editor)"
                    : "") +
                (incomingContentDiffersFromRef
                    ? " (content differs from previous)"
                    : "")
        );

        // Update refs
        contentRef.current = content;
        docIdRef.current = documentId;

        // Use a promise to ensure we don't get stuck in React render loop
        Promise.resolve().then(() => {
            editor.update(() => {
                const root = $getRoot();

                // Always clear first - this is critical!
                root.clear();

                // No content case
                if (!content || content.trim() === "") {
                    root.append($createParagraphNode());
                    return;
                }

                // Handle content with simple paragraphs
                const lines = content.split("\n");
                lines.forEach((line) => {
                    const para = $createParagraphNode();
                    if (line.trim()) {
                        para.append($createTextNode(line));
                    }
                    root.append(para);
                });
            });
        });
    }, [documentId, content, isLoading, editor, getCurrentEditorContent]);

    return null;
}
