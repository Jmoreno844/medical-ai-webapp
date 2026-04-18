import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import { Table } from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import { Markdown } from "@tiptap/markdown";
import { JSONContent } from "@tiptap/react";

export const EMPTY_TIPTAP_DOC: JSONContent = {
  type: "doc",
  content: [{ type: "paragraph" }],
};

export const medicalEditorExtensions = [
  StarterKit.configure({
    link: false,
  }),
  Link.configure({
    openOnClick: false,
    autolink: true,
    linkOnPaste: true,
  }),
  Table.configure({
    resizable: false,
  }),
  TableRow,
  TableHeader,
  TableCell,
  Markdown,
];

export function isTiptapJsonContent(value: unknown): value is JSONContent {
  return typeof value === "object" && value !== null && "type" in value;
}

export function getEmptyTiptapDoc(): JSONContent {
  return JSON.parse(JSON.stringify(EMPTY_TIPTAP_DOC)) as JSONContent;
}
