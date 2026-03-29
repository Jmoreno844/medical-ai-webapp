import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { useEffect, useRef, useState } from "react";
import { $convertToMarkdownString, TRANSFORMERS } from "@lexical/markdown";

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
  const [editor] = useLexicalComposerContext();
  const [, setIsSaving] = useState(false);
  const lastSavedContentRef = useRef<string>("");
  const savingRef = useRef(false);

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
    // Fetch the Markdown version of your content
    const currentContent = getDocumentContent();
    const lastSaved = lastSavedContentRef.current;

    // Skip if content hasn't changed and not forced
    if (
      savingRef.current ||
      (!force && currentContent.trim() === lastSaved.trim())
    ) {
      return;
    }

    // Skip saving empty content if the doc previously had content
    if (hasInitialContent && currentContent.trim() === "") {
      return;
    }

    try {
      savingRef.current = true;
      setIsSaving(true);

      // Save the Markdown content (includes "**" markers)
      await onSave(documentId, currentContent);

      // Only update ref if content hasn't changed during save
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
    if (registerSaveFunction) {
      registerSaveFunction(handleSave);
      return () => registerSaveFunction(() => Promise.resolve());
    }
  }, [registerSaveFunction, documentId]);

  // Auto-save listener
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    let lastSavedContent = lastSavedContentRef.current;

    const removeUpdateListener = editor.registerUpdateListener(() => {
      // Editor content changed, reset any pending save timer
      if (timer) clearTimeout(timer);

      const currentContent = getDocumentContent();
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
  }, [editor, documentId, saveInterval]);

  return null;
}
