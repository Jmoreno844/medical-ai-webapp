import { EditorState, $getRoot } from "lexical";
import { logger } from "@/lib/logger";

/**
 * Extracts plain text content from an editor state
 *
 * @param editorState - The current Lexical editor state
 * @returns Plain text content from the editor
 */
export const getContentFromEditorState = (editorState: EditorState): string => {
  let content = "";

  editorState.read(() => {
    // Check if editor has any content
    const root = $getRoot();
    const hasContent = root.getTextContent().trim().length > 0;

    if (hasContent) {
      // Extract text content directly instead of generating HTML
      content = root.getTextContent();
    }
  });

  return content;
};

/**
 * Cleans HTML content to extract plain text
 *
 * @param html - The HTML content to clean
 * @param removeParagraphTags - Whether to completely remove paragraph tags
 * @returns Clean text content without HTML tags
 */
export const cleanHtml = (html: string, removeParagraphTags = true): string => {
  // If it's empty, return empty string
  if (!html || html.trim().length === 0) return "";

  try {
    // Extract just the text content if we need to completely strip HTML
    if (removeParagraphTags) {
      // Use DOM parser to get cleanest text
      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = html;

      // Get the raw text content
      return tempDiv.textContent || "";
    }

    // Fallback: Use regex to extract text content
    return html.replace(/<[^>]*>/g, "");
  } catch (error) {
    logger.error("HTML cleaning failed:", error);
    // Fallback - use regex to extract text content
    return html.replace(/<[^>]*>/g, "");
  }
};
