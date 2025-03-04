import { useEffect, useRef } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { $getRoot, $createParagraphNode, $createTextNode } from "lexical";
import { $generateNodesFromDOM } from "@lexical/html";

interface DocumentContentPluginProps {
  /**
   * ID of the document being edited
   */
  documentId: number;

  /**
   * Content to load into the editor
   */
  content: string | undefined;

  /**
   * Whether content is currently loading
   */
  isLoading: boolean;
}

/**
 * Plugin that loads document content into the editor
 *
 * @param props - The plugin's properties
 * @returns null - This component doesn't render anything
 */
export function DocumentContentPlugin({
  documentId,
  content,
  isLoading,
}: DocumentContentPluginProps): null {
  const [editor] = useLexicalComposerContext();
  const prevDocumentIdRef = useRef<number>(documentId);
  const prevContentRef = useRef<string | undefined>(content);
  const contentSetRef = useRef<boolean>(false);

  useEffect(() => {
    // Only reinitialize when document or content changes
    if (
      documentId !== prevDocumentIdRef.current ||
      content !== prevContentRef.current
    ) {
      // Don't update if we're loading - wait for content
      if (isLoading) return;

      prevDocumentIdRef.current = documentId;
      prevContentRef.current = content;

      // Skip if content is undefined
      if (content === undefined) return;

      console.log(
        `Setting editor content for doc ${documentId}: "${content.substring(
          0,
          50
        )}..."`
      );

      // Initialize with the content
      const html = content || "";

      // Check if the content is actual HTML or just text
      const isHTML = html.trim().startsWith("<") && html.trim().endsWith(">");

      editor.update(() => {
        const root = $getRoot();
        root.clear();

        if (isHTML) {
          try {
            // Parse HTML content
            const parser = new DOMParser();
            const dom = parser.parseFromString(html, "text/html");

            // Import nodes from DOM
            const nodes = $generateNodesFromDOM(editor, dom);

            // If we got valid nodes, use them
            if (nodes && nodes.length > 0) {
              nodes.forEach((node) => {
                root.append(node);
              });
              contentSetRef.current = true;
              return;
            }
          } catch (error) {
            console.error("Error parsing HTML:", error);
            // Fall through to simple text handling on error
          }
        }

        // Fallback to simple text handling if HTML parsing fails
        // or if the content is not HTML
        const paragraph = $createParagraphNode();
        const text = $createTextNode(html);
        paragraph.append(text);
        root.append(paragraph);
        contentSetRef.current = true;
      });
    }
  }, [editor, content, documentId, isLoading]);

  return null;
}
