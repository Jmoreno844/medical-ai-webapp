import { WorkspaceIndex } from "@/workspace/types";

export type CopilotCapability = "read_only";

export type CopilotSessionResponse = {
  thread_id: string;
  capability: CopilotCapability;
};

export type CopilotMessageRequest = {
  encounter_id: number;
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
  final_response?: string | null;
  applied_patch_id?: string | null;
  applied_document_id?: string | null;
  applied_content?: string | null;
  applied_version?: number | null;
  trace_metadata: Record<string, unknown>;
};

export type CopilotPatchResponse = {
  patch_id: string;
  run_id: string;
  target_document_id: string;
  base_version: number;
  operation_type: string;
  anchor: Record<string, unknown>;
  expected_hash?: string | null;
  before_preview?: string | null;
  after_preview?: string | null;
  document_preview_after?: string | null;
  content_preview: string;
  rationale?: string | null;
  source_context_document_ids: string[];
  target_document_title?: string | null;
  target_selection_reason?: string | null;
  status: "pending" | "approved" | "rejected" | "applied" | "stale";
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
  patches: CopilotPatchResponse[];
};

export type CopilotChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  runId?: string | null;
};

export type CopilotSidePanelTab = "copilot" | "debug";
