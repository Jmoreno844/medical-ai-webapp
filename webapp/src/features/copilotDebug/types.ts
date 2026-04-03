import { WorkspaceIndex } from "@/workspace/types";

export type CopilotCapability = "read_only";

export type CopilotSessionResponse = {
  thread_id: string;
  capability: CopilotCapability;
};

export type CopilotMessageRequest = {
  encounter_id: number;
  thread_id: string;
  user_message: string;
  workspace_index: WorkspaceIndex;
  active_document_id: string | null;
  selected_document_ids: string[];
};

export type CopilotRunResponse = {
  run_id: string;
  thread_id: string;
  status: string;
  intent?: string | null;
  requires_human_review: boolean;
  active_patch_set_id?: string | null;
  applied_patch_set_id?: string | null;
  final_response?: string | null;
  applied_patch_id?: string | null;
  applied_document_id?: string | null;
  applied_content?: string | null;
  applied_version?: number | null;
  trace_metadata: Record<string, unknown>;
};

export type CopilotPatchStatus =
  | "pending"
  | "partially_accepted"
  | "accepted"
  | "rejected"
  | "applied"
  | "stale";

export type CopilotPatchResponse = {
  id: string;
  patchSetId: string;
  documentId: string;
  type: string;
  anchor: Record<string, unknown>;
  oldText: string;
  newText: string;
  resolvedRange: { start: number; end: number };
  orderIndex: number;
  status: CopilotPatchStatus;
  rationale?: string | null;
  confidence?: number | null;
};

export type CopilotPatchSetResponse = {
  id: string;
  run_id: string;
  target_document_id: string;
  base_version: number;
  operation_type: string;
  status: CopilotPatchStatus;
  patches: CopilotPatchResponse[];
  source_context_document_ids: string[];
  target_document_title?: string | null;
  target_selection_reason?: string | null;
  review_comment?: string | null;
  created_at: string;
  updated_at: string;
};

export type CopilotStreamEventName =
  | "run_started"
  | "intent_classified"
  | "agent_decision"
  | "tool_called"
  | "tool_result"
  | "documents_selected"
  | "retrieval_progress"
  | "patch_proposed"
  | "review_required"
  | "patch_applied"
  | "review_resolved"
  | "response_chunk"
  | "run_completed"
  | "run_failed";

export type CopilotStreamEvent = {
  sequence?: number;
  event: CopilotStreamEventName;
  run_id: string;
  thread_id: string;
  created_at?: string;
  payload: Record<string, unknown>;
};

export type CopilotDebugState = {
  threadId: string | null;
  runId: string | null;
  status: string;
  isStreaming: boolean;
  lastError: string | null;
  finalResponse: string | null;
  events: CopilotStreamEvent[];
  patchSets: CopilotPatchSetResponse[];
};

export type CopilotChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  runId?: string | null;
};

export type CopilotSidePanelTab = "copilot" | "debug";
