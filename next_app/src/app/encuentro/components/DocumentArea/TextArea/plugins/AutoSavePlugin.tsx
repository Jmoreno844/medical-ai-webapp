import { useEffect, useRef, useState } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { getContentFromEditorState } from "../utils/contentUtils";

interface AutoSavePluginProps {
  /**
   * Function to save document content
   */
  onSave?: (documentId: number, content: string) => Promise<void>;

  /**
   * ID of the document being edited
   */
  documentId: number;

  /**
   * Function to register the save function with the parent component
   */
  registerSaveFunction?: (saveFunc: (force?: boolean) => Promise<void>) => void;

  /**
   * Whether the document has been loaded with non-empty content
   */
  hasInitialContent: boolean;
}

/**
 * Plugin that handles auto-saving document content
 *
 * @param props - The plugin's properties
 * @returns null - This component doesn't render anything
 */
export function AutoSavePlugin({
  onSave,
  documentId,
  registerSaveFunction,
  hasInitialContent,
}: AutoSavePluginProps): null {
  const [editor] = useLexicalComposerContext();
  const [lastSavedContent, setLastSavedContent] = useState<string>("");
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isTypingRef = useRef<boolean>(false);
  const contentChangedRef = useRef<boolean>(false);
  const documentIdRef = useRef<number>(documentId);
  const savingRef = useRef<boolean>(false);
  const initialContentLoadedRef = useRef<boolean>(hasInitialContent);
  // Add a stabilization delay to prevent premature saving
  const editorStabilizedRef = useRef<boolean>(false);

  // Save content with debounce
  const saveContent = async (force = false) => {
    if (!onSave || !documentIdRef.current || savingRef.current) return;

    // Don't save anything until we're sure the editor has stabilized with real content
    if (!editorStabilizedRef.current && !force) {
      console.log("Editor not stabilized yet, skipping auto-save");
      return;
    }

    try {
      savingRef.current = true;
      const editorState = editor.getEditorState();
      const content = getContentFromEditorState(editorState);

      // CRITICAL: Never save empty content unless it's explicitly typed to be empty
      // This prevents accidentally saving empty content due to timing issues
      if (content.trim() === "" && !force && initialContentLoadedRef.current) {
        console.log(
          "Preventing save of empty content that was previously non-empty"
        );
        savingRef.current = false;
        return;
      }

      // Only save if content changed or force flag is true
      if (
        force ||
        (content !== lastSavedContent && contentChangedRef.current)
      ) {
        console.log(
          `Saving document ${documentId} content (${
            force ? "forced" : "auto"
          }) - Length: ${content.length}`
        );

        // Double-check to ensure we're not saving empty content when there was content before
        if (
          lastSavedContent &&
          lastSavedContent.trim().length > 0 &&
          content.trim() === ""
        ) {
          console.error(
            "Attempted to save empty content when previous content existed - preventing save"
          );
          savingRef.current = false;
          return;
        }

        await onSave(documentIdRef.current, content);
        setLastSavedContent(content);
        contentChangedRef.current = false;
      }
    } catch (error) {
      console.error("Error saving document content:", error);
    } finally {
      isTypingRef.current = false;
      savingRef.current = false;
    }
  };

  // Register the save function with parent component
  useEffect(() => {
    if (registerSaveFunction) {
      registerSaveFunction(saveContent);
    }

    return () => {
      if (registerSaveFunction) {
        registerSaveFunction(() => Promise.resolve());
      }
    };
  }, [registerSaveFunction]);

  // Update tracking reference when document changes
  useEffect(() => {
    documentIdRef.current = documentId;
    initialContentLoadedRef.current = hasInitialContent;
  }, [documentId, hasInitialContent]);

  // Delay to allow editor to stabilize before enabling auto-save
  useEffect(() => {
    const stabilizationTimer = setTimeout(() => {
      editorStabilizedRef.current = true;
      console.log("Editor stabilized, auto-save enabled");
    }, 2000); // Give 2 seconds for the editor to fully initialize

    return () => clearTimeout(stabilizationTimer);
  }, [documentId]); // Reset this timer when the document changes

  // Handle blur events for auto-save
  useEffect(() => {
    const handleBlur = async () => {
      if (
        (isTypingRef.current || contentChangedRef.current) &&
        editorStabilizedRef.current
      ) {
        await saveContent();
      }
    };

    window.addEventListener("blur", handleBlur);
    return () => {
      window.removeEventListener("blur", handleBlur);
    };
  }, []);

  // Register for editor updates
  useEffect(() => {
    return editor.registerUpdateListener(({ editorState }) => {
      const content = getContentFromEditorState(editorState);

      // Record if we've loaded initial content (non-empty)
      if (
        content &&
        content.trim().length > 0 &&
        !initialContentLoadedRef.current
      ) {
        initialContentLoadedRef.current = true;
        console.log(
          "Initial content loaded into editor:",
          content.substring(0, 50) + "..."
        );
      }

      isTypingRef.current = true;
      contentChangedRef.current = true;

      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      // Only enable auto-save timeout after stabilization
      if (editorStabilizedRef.current) {
        saveTimeoutRef.current = setTimeout(() => saveContent(), 1500);
      }
    });
  }, [editor, onSave]);

  // Cleanup on unmount - ensure content is saved
  useEffect(() => {
    return () => {
      if (
        (isTypingRef.current || contentChangedRef.current) &&
        editorStabilizedRef.current
      ) {
        // We must use an immediate save here since the component is unmounting
        saveContent(true);
      }

      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  return null;
}
