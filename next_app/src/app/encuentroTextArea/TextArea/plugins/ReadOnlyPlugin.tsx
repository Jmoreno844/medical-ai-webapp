import { useEffect } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";

interface ReadOnlyPluginProps {
  /**
   * Whether the editor should be in read-only mode
   */
  isReadOnly: boolean;
}

/**
 * Plugin that controls the editor's read-only state
 *
 * @param props - The plugin's properties
 * @returns null - This component doesn't render anything
 */
export function ReadOnlyPlugin({ isReadOnly }: ReadOnlyPluginProps): null {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    // Set the editor's editable state based on the isReadOnly prop
    editor.setEditable(!isReadOnly);
  }, [editor, isReadOnly]);

  return null;
}
