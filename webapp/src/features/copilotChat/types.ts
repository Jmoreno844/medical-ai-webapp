import { WorkspaceIndex } from "@/workspace/types";

export type CopilotCapability = "read_only";

/** Maps backend section slugs to human-readable Spanish labels */
export const SECTION_DISPLAY_NAMES: Record<string, string> = {
  datos_basicos: "Datos básicos",
  motivo_consulta: "Motivo de consulta",
  enfermedad_actual: "Enfermedad actual",
  revision_sistemas: "Revisión por sistemas",
  antecedentes: "Antecedentes",
  signos_vitales: "Signos vitales",
  examen_fisico: "Examen físico",
  impresion_diagnostica: "Impresión diagnóstica",
  analisis_clinico: "Análisis clínico",
  plan_manejo: "Plan de manejo",
  cierre: "Cierre",
  // Generic fallback keys the agent may use
  general: "General",
  tratamiento: "Tratamiento",
  diagnostico: "Diagnóstico",
};

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
  | "conflicted"
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
  resolvedRange: { start: number; end: number } | null;
  orderIndex: number;
  status: CopilotPatchStatus;
  rationale?: string | null;
  confidence?: number | null;
  /** Semantic section key (e.g. 'datos_basicos') from the clinical plan */
  section?: string | null;
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
  /** Scope of the edit: 'local' | 'propagation' | 'full_rewrite' */
  edit_scope?: string | null;
  /** Clinical impact level: 'low' | 'medium' | 'high' | 'critical' */
  clinical_impact_level?: string | null;
  /** Section slugs that this patch set affects */
  affected_sections?: string[];
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
  /** When set, this message renders as a compact resolved patch card instead of text. */
  patchCard?: {
    patchSet: CopilotPatchSetResponse;
    outcome: "applied" | "rejected";
  } | null;
};

export type CopilotSidePanelTab = "copilot" | "debug";
