import { DocumentoOut } from "@/types/documento";

export type DocumentJsonContent = Record<string, unknown> | null;

export type WorkspaceDocumentType =
  | "note"
  | "transcription"
  | "context"
  | "template"
  | "uploaded_document"
  | "generated_document"
  | "mipres_draft"
  | "patient_history_summary";

export type WorkspaceDocumentStatus =
  | "draft"
  | "streaming"
  | "suggested"
  | "reviewed"
  | "final"
  | "read_only";

export type WorkspaceDocumentSource =
  | "user"
  | "transcription"
  | "ai"
  | "external"
  | "system";

export type WorkspaceEditorMode =
  | "edit"
  | "read_only"
  | "streaming_preview"
  | "patch_review";

export type DocumentDerivedSource =
  | "generation"
  | "transcription"
  | "patch_review"
  | "system";

export type TranscriptionProcessStatus =
  | "idle"
  | "pending"
  | "success"
  | "error";

export type WorkspaceDocument = {
  id: string;
  encounterId: string;
  type: WorkspaceDocumentType;
  title: string;
  status: WorkspaceDocumentStatus;
  source: WorkspaceDocumentSource;
  aiReadable: boolean;
  aiWritable: boolean;
  userEditable: boolean;
  version: number;
  contentMarkdown: string;
  contentJson?: DocumentJsonContent;
  metadata: Record<string, unknown>;
  summaryShort?: string;
  summaryClinical?: string;
  contentHash?: string;
  estimatedTokens?: number;
  createdAt: string;
  updatedAt: string;
};

export type DocumentSection = {
  id: string;
  title: string;
  contentMarkdown: string;
  order: number;
  semanticTag?: string;
  userDefined: boolean;
  aiWritable: boolean;
  copyable: boolean;
};

export type DocumentSnapshot = {
  documentId: string;
  version: number;
  contentMarkdown: string;
  contentJson?: DocumentJsonContent;
  sections?: DocumentSection[];
  savedAt: string;
};

export type DocumentDraftState = {
  documentId: string;
  localUnsavedContent: string | null;
  localUnsavedContentJson?: DocumentJsonContent;
  localSections?: DocumentSection[];
  isDirty: boolean;
  lastEditedAt?: string;
  // True when the doctor typed in this document since the last copilot turn.
  // Survives autosave (which clears isDirty) and is reset only after a
  // successful copilot submission. Used to emit <user_edit_notices> to the agent.
  userEditedSinceLastCopilotTurn?: boolean;
};

export type DocumentDerivedState = {
  documentId: string;
  editorMode: WorkspaceEditorMode;
  source?: DocumentDerivedSource;
  inProgress: boolean;
  isComplete: boolean;
  error: string | null;
  updatedAt: string;
  processingId?: string | null;
  transcriptionStatus?: TranscriptionProcessStatus;
  streamingContent?: string;
  patchPreviewContent?: string;
  regeneratedSummary?: string;
};

export type DocumentPatchOperationType =
  | "append_text"
  | "replace_range"
  | "replace_section"
  | "insert_after_section"
  | "create_document"
  | "update_title";

export type DocumentPatchStatus =
  | "pending"
  | "accepted"
  | "rejected"
  | "applied"
  | "stale";

export type DocumentPatch = {
  id: string;
  documentId: string;
  documentVersionBase: number;
  createdBy: "ai" | "user" | "system";
  sourceContextDocumentIds: string[];
  operationType: DocumentPatchOperationType;
  summary: string;
  rationale?: string;
  targetSectionId?: string;
  beforeContent?: string;
  afterContent: string;
  status: DocumentPatchStatus;
  createdAt: string;
  acceptedAt?: string;
  rejectedAt?: string;
};

export type WorkspaceIndex = {
  encounterId: string;
  workspaceVersion: string;
  activeDocumentId: string | null;
  openDocumentIds: string[];
  documents: Array<{
    documentId: string;
    type: WorkspaceDocumentType;
    title: string;
    status: WorkspaceDocumentStatus;
    source: WorkspaceDocumentSource;
    aiReadable: boolean;
    aiWritable: boolean;
    version: number;
    updatedAt: string;
    isActive: boolean;
    isOpen: boolean;
    hasDirtyDraft: boolean;
    // True when the doctor typed in this document since the last copilot turn,
    // even if autosave already flushed isDirty to false.
    hasUserEdits: boolean;
    hasStreamingState: boolean;
    hiddenFromAgent: boolean;
    pinnedForAgent: boolean;
    estimatedTokens?: number;
    hasPendingPatches?: boolean;
    // Full markdown content for ai_writable docs — sent so the agent can propose
    // patches without a separate read_document round-trip. Only present for docs
    // the frontend decides to pre-load (open + ai_writable). Read-only or
    // hidden docs never carry this field.
    contentMarkdown?: string;
    contentJson?: DocumentJsonContent;
  }>;
};

export type ReadMode = "index" | "summary" | "sections" | "range" | "full";

export type AiSessionReadMode = "active_only" | "working_set" | "all_readable";

export type WorkspaceLegacyDocument = DocumentoOut;
