import { HeadingNode, QuoteNode } from "@lexical/rich-text";
import { ListItemNode, ListNode } from "@lexical/list";
import { CodeHighlightNode, CodeNode } from "@lexical/code";
import { TableCellNode, TableNode, TableRowNode } from "@lexical/table";
import { LinkNode } from "@lexical/link";

/**
 * Custom theme for the Lexical editor
 */
export const editorTheme = {
  root: "p-0 h-full min-h-[300px] outline-none",
  paragraph: "mb-3 leading-normal",
  heading: {
    h1: "text-2xl font-bold mb-4",
    h2: "text-xl font-bold mb-3",
    h3: "text-lg font-bold mb-2",
  },
  list: {
    ul: "list-disc ml-5 mb-3",
    ol: "list-decimal ml-5 mb-3",
  },
  text: {
    bold: "font-bold",
    italic: "italic",
    underline: "underline",
  },
};

/**
 * Nodes to register with the Lexical editor
 */
export const editorNodes = [
  HeadingNode,
  ListNode,
  ListItemNode,
  QuoteNode,
  CodeNode,
  CodeHighlightNode,
  TableNode,
  TableCellNode,
  TableRowNode,
  LinkNode,
];

/**
 * Creates the initial configuration for the Lexical editor
 *
 * @param onError - Error handler callback
 * @returns Initial editor configuration
 */
export const createEditorConfig = (onError: (error: Error) => void) => {
  return {
    namespace: "MedicalDocumentEditor",
    theme: editorTheme,
    onError,
    nodes: editorNodes,
  };
};
