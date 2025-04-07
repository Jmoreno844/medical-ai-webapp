import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { useEffect, useRef, useState } from "react";
import { $convertToMarkdownString, TRANSFORMERS } from "@lexical/markdown";
import { $getRoot } from "lexical";

interface AutoSavePluginProps {
  documentId: number;
  onSave: (docId: number, content: string) => Promise<void>;
  registerSaveFunction?: (saveFunc: (force?: boolean) => Promise<void>) => void;
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
  // Implementation stays largely the same
  const [editor] = useLexicalComposerContext();
  const [isSaving, setIsSaving] = useState(false);
  const lastSavedContentRef = useRef<string>("");
  const savingRef = useRef(false);
  const contentBeforeSaveRef = useRef("");

  // Convert editor state to Markdown (retaining ** markers) instead of just plain text
  const getDocumentContent = (): string => {
    let content = "";
    editor.getEditorState().read(() => {
      // Convert all current editor content to Markdown
      content = $convertToMarkdownString(TRANSFORMERS);
    });
    return content;
  };

  const handleSave = async (force: boolean = false) => {
    // ...existing code...
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
      console.error(
        `[AUTO_SAVE] Failed to save document ${documentId}:`,
        error
      );
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  };

  // Register save function with the parent component
  useEffect(() => {
    // ...existing code...
    if (registerSaveFunction) {
      registerSaveFunction(handleSave);
      return () => registerSaveFunction(() => Promise.resolve());
    }
  }, [registerSaveFunction, documentId]);

  // Auto-save listener
  useEffect(() => {
    // ...existing code...
    let timer: NodeJS.Timeout | null = null;
    let lastSavedContent = lastSavedContentRef.current;

    const removeUpdateListener = editor.registerUpdateListener(() => {
      if (timer) clearTimeout(timer);

      const currentContent = getDocumentContent();
      if (currentContent !== lastSavedContent) {
        lastSavedContent = currentContent;
        timer = setTimeout(() => handleSave(false), saveInterval);
      }
    });

    return () => {
      removeUpdateListener();
      if (timer) clearTimeout(timer);
    };
  }, [editor, documentId, saveInterval]);

  return null;
}
