import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { useEffect, useRef, useState } from "react";
import { $getRoot, $isElementNode, EditorState } from "lexical";

interface AutoSavePluginProps {
    documentId: number;
    onSave: (docId: number, content: string) => Promise<void>;
    registerSaveFunction?: (
        saveFunc: (force?: boolean) => Promise<void>
    ) => void;
    hasInitialContent?: boolean;
    saveInterval?: number; // Time in ms for auto-save
}

export function AutoSavePlugin({
    documentId,
    onSave,
    registerSaveFunction,
    hasInitialContent = false,
    saveInterval = 2000,
}: AutoSavePluginProps) {
    const [editor] = useLexicalComposerContext();
    const [isSaving, setIsSaving] = useState(false);
    const lastSavedContentRef = useRef<string>("");
    const isProgrammaticUpdateRef = useRef<boolean>(false);
    const savingRef = useRef(false);
    const contentBeforeSaveRef = useRef("");

    // Get document content from Lexical editor
    const getDocumentContent = (): string => {
        let content = "";

        editor.getEditorState().read(() => {
            const root = $getRoot();
            content = root.getTextContent();
        });

        return content;
    };

    const handleSave = async (force: boolean = false) => {
        // Get current content
        const currentContent = getDocumentContent();
        const lastSaved = lastSavedContentRef.current;

        // Skip if content hasn't changed and not forced
        if (!force && currentContent.trim() === lastSaved.trim()) {
            console.log(
                `[AUTO_SAVE] Document ${documentId}: Content unchanged, skipping save`
            );
            return;
        }

        console.log(
            `[AUTO_SAVE] Saving document ${documentId} content` +
                (force ? " (forced)" : "") +
                ` - Length: ${currentContent.length} chars`
        );

        // Skip if already saving
        if (savingRef.current) {
            console.log(
                `[AUTO_SAVE] Document ${documentId}: Already saving, request queued`
            );
            return;
        }

        // Skip empty content if we previously had content (to prevent data loss)
        if (hasInitialContent && currentContent.trim() === "") {
            console.log(
                "[AUTO_SAVE] Preventing save of empty content when document previously had content"
            );
            return;
        }

        // Store content for comparison
        contentBeforeSaveRef.current = currentContent;

        try {
            savingRef.current = true;
            setIsSaving(true);

            await onSave(documentId, currentContent);

            // Only update ref if content hasn't changed during save
            if (contentBeforeSaveRef.current === getDocumentContent()) {
                lastSavedContentRef.current = currentContent;
            }
            console.log(
                `[AUTO_SAVE] Document ${documentId} saved successfully`
            );
        } catch (error) {
            console.error(
                `[AUTO_SAVE] Failed to save document ${documentId}:`,
                error
            );
        } finally {
            savingRef.current = false;
            setIsSaving(false);
        }
    };

    // Register save function with parent component
    useEffect(() => {
        if (registerSaveFunction) {
            registerSaveFunction(handleSave);
            return () => registerSaveFunction(() => Promise.resolve());
        }
    }, [registerSaveFunction, documentId]);

    // Set up auto-save on editor changes
    useEffect(() => {
        let timer: NodeJS.Timeout | null = null;
        let lastSavedContent = lastSavedContentRef.current;

        const removeUpdateListener = editor.registerUpdateListener(
            ({ editorState }) => {
                // Skip auto-save if this is a programmatic update
                if (isProgrammaticUpdateRef.current) {
                    return;
                }

                // Get current content and compare with last saved
                const currentContent = getDocumentContent();
                if (currentContent === lastSavedContent) {
                    return;
                }

                // Clear existing timer
                if (timer) {
                    clearTimeout(timer);
                }

                // Update local reference for comparison
                lastSavedContent = currentContent;

                // Set new timer for auto-save
                timer = setTimeout(() => {
                    handleSave(false);
                }, saveInterval);
            }
        );

        // Clean up
        return () => {
            removeUpdateListener();
            if (timer) {
                clearTimeout(timer);
            }
        };
    }, [editor, documentId]);

    return null;
}
