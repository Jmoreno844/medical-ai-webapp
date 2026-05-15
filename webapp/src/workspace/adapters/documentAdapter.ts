import { DOCUMENT_TYPE_LABELS_LONG, DocumentoOut } from "@/types/documento";
import {
  WorkspaceDocument,
  WorkspaceDocumentSource,
  WorkspaceDocumentStatus,
  WorkspaceDocumentType,
} from "@/workspace/types";

function mapKindToWorkspaceType(kind: string): WorkspaceDocumentType {
  switch (kind) {
    case "transcription":
      return "transcription";
    case "context":
      return "context";
    case "template":
      return "template";
    case "note":
      return "note";
    default:
      return "generated_document";
  }
}

function getWorkspaceStatus(kind: string): WorkspaceDocumentStatus {
  switch (kind) {
    case "transcription":
      return "read_only";
    case "context":
      return "final";
    default:
      return "draft";
  }
}

function getWorkspaceSource(kind: string): WorkspaceDocumentSource {
  switch (kind) {
    case "transcription":
      return "transcription";
    case "context":
      return "system";
    case "note":
      return "user";
    default:
      return "system";
  }
}

export function adaptDocumentoToWorkspaceDocument(
  doc: DocumentoOut,
  encounterId?: number | string,
): WorkspaceDocument {
  const resolvedEncounterId = String(encounterId ?? doc.encounter_id);
  const type = mapKindToWorkspaceType(doc.kind);
  const title =
    doc.doctor_template_name ||
    DOCUMENT_TYPE_LABELS_LONG[doc.kind.toLowerCase()] ||
    doc.kind;
  const isReadOnly = doc.kind === "transcription";
  const isAiWritable = doc.kind !== "transcription";

  return {
    id: String(doc.id),
    encounterId: resolvedEncounterId,
    type,
    title,
    status: getWorkspaceStatus(doc.kind),
    source: getWorkspaceSource(doc.kind),
    aiReadable: true,
    aiWritable: isAiWritable,
    userEditable: !isReadOnly,
    version: 1,
    contentMarkdown: doc.content_markdown ?? doc.content ?? "",
    contentJson: doc.content_json ?? null,
    metadata: {
      kind: doc.kind,
      created_on: doc.created_on,
      doctor_id: doc.doctor_id,
      doctor_template_id: doc.doctor_template_id ?? null,
      doctor_template_name: doc.doctor_template_name ?? null,
      encounter_id: doc.encounter_id,
    },
    createdAt: doc.created_on,
    updatedAt: doc.created_on,
  };
}

export function adaptWorkspaceDocumentToDocumentoOut(
  doc: WorkspaceDocument,
): DocumentoOut {
  return {
    id: Number(doc.id),
    encounter_id: Number(doc.encounterId),
    kind: String(doc.metadata.kind ?? doc.type),
    doctor_template_id:
      typeof doc.metadata.doctor_template_id === "number" ||
      doc.metadata.doctor_template_id === null
        ? (doc.metadata.doctor_template_id as number | null)
        : null,
    doctor_template_name:
      typeof doc.metadata.doctor_template_name === "string" ||
      doc.metadata.doctor_template_name === null
        ? (doc.metadata.doctor_template_name as string | null)
        : null,
    content: doc.contentMarkdown,
    content_markdown: doc.contentMarkdown,
    content_json:
      typeof doc.contentJson === "undefined" ? null : (doc.contentJson ?? null),
    created_on: String(doc.metadata.created_on ?? doc.createdAt),
    doctor_id: Number(doc.metadata.doctor_id ?? 0),
  };
}
