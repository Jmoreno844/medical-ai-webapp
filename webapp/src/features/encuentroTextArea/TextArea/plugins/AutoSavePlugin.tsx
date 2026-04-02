import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { useCallback, useEffect, useRef, useState } from "react";
import { $convertToMarkdownString, TRANSFORMERS } from "@lexical/markdown";

import { logger } from "@/lib/logger";
interface AutoSavePluginProps {
  documentId: number;
  onSave: (docId: number, content: string) => Promise<void>;
  onDraftChange?: (docId: number, content: string) => void;
  registerSaveFunction?: (saveFunc: (force?: boolean) => Promise<void>) => void;
  hasInitialContent?: boolean;
  saveInterval?: number; // Time in ms for auto-save
}

export function AutoSavePlugin({
  documentId,
  onSave,
  onDraftChange,
  registerSaveFunction,
  hasInitialContent = false,
  saveInterval = 2000,
}: AutoSavePluginProps) {
  const [editor] = useLexicalComposerContext();
  const [, setIsSaving] = useState(false);
  const lastSavedContentRef = useRef<string>("");
  const savingRef = useRef(false);

  // Convert editor state to Markdown (retaining ** markers) instead of just plain text
  const getDocumentContent = useCallback((): string => {
    let content = "";
    editor.getEditorState().read(() => {
      content = $convertToMarkdownString(TRANSFORMERS);
    });
    return content;
  }, [editor]);

  const handleSave = useCallback(
    async (force: boolean = false) => {
      const currentContent = getDocumentContent();
      const lastSaved = lastSavedContentRef.current;

      if (
        savingRef.current ||
        (!force && currentContent.trim() === lastSaved.trim())
      ) {
        return;
      }

      if (hasInitialContent && currentContent.trim() === "") {
        return;
      }

      try {
        savingRef.current = true;
        setIsSaving(true);

        await onSave(documentId, currentContent);

        if (currentContent === getDocumentContent()) {
          lastSavedContentRef.current = currentContent;
        }
      } catch (error) {
        logger.error(
          `[AUTO_SAVE] Failed to save document ${documentId}:`,
          error
        );
      } finally {
        savingRef.current = false;
        setIsSaving(false);
      }
    },
    [documentId, getDocumentContent, hasInitialContent, onSave]
  );

  // Register save function with the parent component
  useEffect(() => {
    if (registerSaveFunction) {
      registerSaveFunction(handleSave);
      return () => registerSaveFunction(() => Promise.resolve());
    }
  }, [handleSave, registerSaveFunction]);

  // Auto-save listener
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    let lastSavedContent = lastSavedContentRef.current;

    const removeUpdateListener = editor.registerUpdateListener(() => {
      // Editor content changed, reset any pending save timer
      if (timer) clearTimeout(timer);

      const currentContent = getDocumentContent();
      onDraftChange?.(documentId, currentContent);

      // Only schedule a save if new content is different
      if (currentContent !== lastSavedContent) {
        lastSavedContent = currentContent;
        timer = setTimeout(() => handleSave(false), saveInterval);
      }
    });

    return () => {
      removeUpdateListener();
      if (timer) clearTimeout(timer);
    };
  }, [documentId, editor, getDocumentContent, handleSave, onDraftChange, saveInterval]);

  return null;
}
