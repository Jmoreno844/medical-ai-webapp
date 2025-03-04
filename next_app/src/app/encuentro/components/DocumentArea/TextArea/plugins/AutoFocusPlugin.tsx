import { useEffect } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";

/**
 * Plugin that automatically focuses the editor when loaded
 *
 * @returns null - This component doesn't render anything
 */
export function AutoFocusPlugin(): null {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    // Focus the editor when the component mounts
    editor.focus();
  }, [editor]);

  return null;
}
