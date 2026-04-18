import axiosInstance from "@/commons/utils/axiosInstance";
import {
  CopilotMessageRequest,
  CopilotNormalizedPatchOperationType,
  CopilotPatchAnchor,
  CopilotPatchOperationType,
  CopilotPatchResponse,
  CopilotPatchSetResponse,
  CopilotRunResponse,
  CopilotSessionResponse,
  CopilotStreamEvent,
} from "@/features/copilotChat/types";
import { WorkspaceIndex } from "@/workspace/types";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

type CopilotPatchApi = {
  id?: string;
  patch_id?: string;
  patchSetId?: string;
  patch_set_id?: string;
  documentId?: string;
  target_document_id?: string;
  type?: string;
  patch_type?: string;
  operation_type?: string;
  normalized_operation_type?: string;
  anchor?: Record<string, unknown>;
  replacement_text?: string;
  inserted_text?: string;
  oldText?: string;
  old_text?: string;
  newText?: string;
  new_text?: string;
  resolvedRange?: { start: number; end: number };
  resolved_range?: { start: number; end: number };
  resolved_start?: number;
  resolved_end?: number;
  orderIndex?: number;
  order_index?: number;
  status?: CopilotPatchResponse["status"];
  rationale?: string | null;
  confidence?: number | null;
  section?: string | null;
};

type CopilotPatchSetApi = {
  id?: string;
  patch_set_id?: string;
  run_id: string;
  target_document_id: string;
  base_version: number;
  operation_type?: string;
  status: CopilotPatchSetResponse["status"];
  patches?: CopilotPatchApi[];
  source_context_document_ids?: string[];
  target_document_title?: string | null;
  target_selection_reason?: string | null;
  review_comment?: string | null;
  created_at?: string;
  updated_at?: string;
  edit_scope?: string | null;
  clinical_impact_level?: string | null;
  affected_sections?: string[];
};

function normalizePatchOperationType(
  value: unknown,
): CopilotNormalizedPatchOperationType {
  const operationType = String(value ?? "")
    .trim()
    .toLowerCase();
  if (
    operationType === "insert_after" ||
    operationType === "insert_after_span"
  ) {
    return "insert_after";
  }
  if (operationType === "insert_before") {
    return "insert_before";
  }
  if (operationType === "delete_span") {
    return "delete_span";
  }
  return "replace_span";
}

function normalizeLegacyPatchOperationType(
  value: unknown,
): CopilotPatchOperationType {
  const operationType = String(value ?? "")
    .trim()
    .toLowerCase();
  if (
    operationType === "replace_span" ||
    operationType === "insert_before" ||
    operationType === "insert_after" ||
    operationType === "insert_after_span" ||
    operationType === "delete_span" ||
    operationType === "rewrite_document"
  ) {
    return operationType;
  }
  return "replace_span";
}

function normalizePatchAnchor(anchor: unknown): CopilotPatchAnchor {
  if (!anchor || typeof anchor !== "object") {
    return {};
  }

  const candidate = anchor as Record<string, unknown>;
  return {
    exactText:
      typeof candidate.exactText === "string" ? candidate.exactText : null,
    prefixText:
      typeof candidate.prefixText === "string" ? candidate.prefixText : null,
    suffixText:
      typeof candidate.suffixText === "string" ? candidate.suffixText : null,
    startOffset:
      typeof candidate.startOffset === "number" ? candidate.startOffset : null,
    endOffset:
      typeof candidate.endOffset === "number" ? candidate.endOffset : null,
  };
}

function normalizePatch(
  apiPatch: CopilotPatchApi,
  parentPatchSetId: string,
): CopilotPatchResponse {
  const resolvedRange =
    apiPatch.resolvedRange ??
    apiPatch.resolved_range ??
    (typeof apiPatch.resolved_start === "number"
      ? {
          start: apiPatch.resolved_start,
          end:
            typeof apiPatch.resolved_end === "number"
              ? apiPatch.resolved_end
              : apiPatch.resolved_start,
        }
      : null);
  const operationType = normalizeLegacyPatchOperationType(
    apiPatch.operation_type ?? apiPatch.patch_type ?? apiPatch.type,
  );
  const normalizedOperationType = normalizePatchOperationType(
    apiPatch.normalized_operation_type ??
      apiPatch.patch_type ??
      apiPatch.operation_type ??
      apiPatch.type,
  );

  return {
    id: String(apiPatch.id ?? apiPatch.patch_id ?? ""),
    patchSetId: String(
      apiPatch.patchSetId ?? apiPatch.patch_set_id ?? parentPatchSetId,
    ),
    documentId: String(
      apiPatch.documentId ?? apiPatch.target_document_id ?? "",
    ),
    type: normalizedOperationType,
    operationType,
    normalizedOperationType,
    anchor: normalizePatchAnchor(apiPatch.anchor),
    replacementText: apiPatch.replacement_text ?? null,
    insertedText: apiPatch.inserted_text ?? null,
    oldText: String(apiPatch.oldText ?? apiPatch.old_text ?? ""),
    newText: String(apiPatch.newText ?? apiPatch.new_text ?? ""),
    resolvedRange,
    orderIndex: Number(apiPatch.orderIndex ?? apiPatch.order_index ?? 0),
    status: apiPatch.status ?? "pending",
    rationale: apiPatch.rationale ?? null,
    confidence: apiPatch.confidence ?? null,
    section: apiPatch.section ?? null,
  };
}

function normalizePatchSets(response: unknown): CopilotPatchSetResponse[] {
  if (!Array.isArray(response)) {
    return [];
  }

  // New backend contract: list of patch sets.
  if (
    response.length === 0 ||
    (typeof response[0] === "object" &&
      response[0] !== null &&
      "patches" in response[0])
  ) {
    return (response as CopilotPatchSetApi[]).map((patchSet) => {
      const patchSetId = String(patchSet.id ?? patchSet.patch_set_id ?? "");
      return {
        id: patchSetId,
        run_id: patchSet.run_id,
        target_document_id: String(patchSet.target_document_id ?? ""),
        base_version: Number(patchSet.base_version ?? 1),
        operation_type: String(patchSet.operation_type ?? "replace_span"),
        status: patchSet.status ?? "pending",
        patches: Array.isArray(patchSet.patches)
          ? patchSet.patches.map((patch) => normalizePatch(patch, patchSetId))
          : [],
        source_context_document_ids: patchSet.source_context_document_ids ?? [],
        target_document_title: patchSet.target_document_title ?? null,
        target_selection_reason: patchSet.target_selection_reason ?? null,
        review_comment: patchSet.review_comment ?? null,
        created_at: patchSet.created_at ?? new Date().toISOString(),
        updated_at: patchSet.updated_at ?? new Date().toISOString(),
        edit_scope: patchSet.edit_scope ?? null,
        clinical_impact_level: patchSet.clinical_impact_level ?? null,
        affected_sections: patchSet.affected_sections ?? [],
      };
    });
  }

  // Legacy fallback: list of flat patches from /patches.
  const patches = response as CopilotPatchApi[];
  const groupedByPatchSet = new Map<string, CopilotPatchApi[]>();
  for (const patch of patches) {
    const patchSetId = String(
      patch.patchSetId ??
        patch.patch_set_id ??
        `legacy-${patch.id ?? patch.patch_id ?? "unknown"}`,
    );
    const existing = groupedByPatchSet.get(patchSetId) ?? [];
    existing.push(patch);
    groupedByPatchSet.set(patchSetId, existing);
  }

  return Array.from(groupedByPatchSet.entries()).map(
    ([patchSetId, groupedPatches]) => {
      const firstPatch = groupedPatches[0];
      return {
        id: patchSetId,
        run_id: String((firstPatch as { run_id?: unknown }).run_id ?? ""),
        target_document_id: String(firstPatch.target_document_id ?? ""),
        base_version: Number(
          (firstPatch as { base_version?: unknown }).base_version ?? 1,
        ),
        operation_type: String(firstPatch.operation_type ?? "replace_span"),
        status:
          (firstPatch.status as CopilotPatchSetResponse["status"]) ?? "pending",
        patches: groupedPatches.map((patch) =>
          normalizePatch(patch, patchSetId),
        ),
        source_context_document_ids: [],
        target_document_title: null,
        target_selection_reason: null,
        review_comment: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
    },
  );
}

function serializeWorkspaceIndex(workspaceIndex: WorkspaceIndex) {
  return {
    encounter_id: workspaceIndex.encounterId,
    workspace_version: workspaceIndex.workspaceVersion,
    active_document_id: workspaceIndex.activeDocumentId,
    open_document_ids: workspaceIndex.openDocumentIds,
    documents: workspaceIndex.documents.map((document) => ({
      document_id: document.documentId,
      type: document.type,
      title: document.title,
      status: document.status,
      source: document.source,
      ai_readable: document.aiReadable,
      ai_writable: document.aiWritable,
      version: document.version,
      updated_at: document.updatedAt,
      is_active: document.isActive,
      is_open: document.isOpen,
      has_dirty_draft: document.hasDirtyDraft,
      has_user_edits: document.hasUserEdits,
      has_streaming_state: document.hasStreamingState,
      hidden_from_agent: document.hiddenFromAgent,
      pinned_for_agent: document.pinnedForAgent,
      estimated_tokens: document.estimatedTokens,
      has_pending_patches: document.hasPendingPatches,
      content_markdown: document.contentMarkdown,
      content_json: document.contentJson,
    })),
  };
}

export async function createCopilotSession(encounterId: number) {
  const response = await axiosInstance.post<CopilotSessionResponse>(
    "/api/copilot/sessions",
    {
      encounter_id: encounterId,
    },
  );

  return response.data;
}

export async function sendCopilotMessage(payload: CopilotMessageRequest) {
  const response = await axiosInstance.post<CopilotRunResponse>(
    "/api/copilot/messages",
    {
      encounter_id: payload.encounter_id,
      thread_id: payload.thread_id,
      user_message: payload.user_message,
      workspace_index: serializeWorkspaceIndex(payload.workspace_index),
      active_document_id: payload.active_document_id,
      selected_document_ids: payload.selected_document_ids,
    },
  );

  return response.data;
}

export async function getCopilotRun(runId: string) {
  const response = await axiosInstance.get<CopilotRunResponse>(
    `/api/copilot/runs/${runId}`,
  );

  return response.data;
}

export async function listCopilotPatchSets(runId: string) {
  const response = await axiosInstance.get<unknown>(
    `/api/copilot/runs/${runId}/patch-sets`,
  );

  return normalizePatchSets(response.data);
}

export async function reviewCopilotPatch(
  runId: string,
  payload: {
    patch_id: string;
    decision: "approve" | "reject";
    comment?: string | null;
    document_version?: number;
  },
) {
  const response = await axiosInstance.post<CopilotRunResponse>(
    `/api/copilot/runs/${runId}/review`,
    payload,
  );

  return response.data;
}

export async function acceptCopilotPatch(
  patchSetId: string,
  payload: {
    patch_id: string;
    comment?: string | null;
  },
) {
  const response = await axiosInstance.post<CopilotPatchSetResponse>(
    `/api/copilot/patch-sets/${patchSetId}/accept-patch`,
    payload,
  );

  return normalizePatchSets([response.data])[0];
}

export async function rejectCopilotPatch(
  patchSetId: string,
  payload: {
    patch_id: string;
    comment?: string | null;
  },
) {
  const response = await axiosInstance.post<CopilotPatchSetResponse>(
    `/api/copilot/patch-sets/${patchSetId}/reject-patch`,
    payload,
  );

  return normalizePatchSets([response.data])[0];
}

export async function acceptAllCopilotPatches(
  patchSetId: string,
  payload: {
    comment?: string | null;
  },
) {
  const response = await axiosInstance.post<CopilotPatchSetResponse>(
    `/api/copilot/patch-sets/${patchSetId}/accept-all`,
    payload,
  );

  return normalizePatchSets([response.data])[0];
}

export async function rejectAllCopilotPatches(
  patchSetId: string,
  payload: {
    comment?: string | null;
  },
) {
  const response = await axiosInstance.post<CopilotPatchSetResponse>(
    `/api/copilot/patch-sets/${patchSetId}/reject-all`,
    payload,
  );

  return normalizePatchSets([response.data])[0];
}

export async function applyAcceptedCopilotPatchSet(
  patchSetId: string,
  payload: {
    comment?: string | null;
    document_version?: number;
  },
) {
  const response = await axiosInstance.post<CopilotRunResponse>(
    `/api/copilot/patch-sets/${patchSetId}/apply-accepted`,
    payload,
  );

  return response.data;
}

export async function finalizeCopilotPatchSetReview(
  patchSetId: string,
  payload: {
    comment?: string | null;
    document_version?: number;
  },
) {
  const response = await axiosInstance.post<CopilotRunResponse>(
    `/api/copilot/patch-sets/${patchSetId}/finalize-review`,
    payload,
  );

  return response.data;
}

export function streamCopilotRun(
  runId: string,
  afterSequence: number,
  handlers: {
    onEvent: (event: CopilotStreamEvent) => void;
    onError: (message: string) => void;
    onOpen?: () => void;
  },
) {
  const params = new URLSearchParams();
  if (afterSequence > 0) {
    params.set("after_sequence", String(afterSequence));
  }
  const streamUrl = `${API_URL}/api/copilot/runs/${runId}/stream${
    params.size > 0 ? `?${params.toString()}` : ""
  }`;
  const eventSource = new EventSource(streamUrl, { withCredentials: true });
  let terminalEventSeen = false;

  const handleNamedEvent = (eventName: CopilotStreamEvent["event"]) => {
    eventSource.addEventListener(eventName, (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent<string>).data);
        const streamEvent: CopilotStreamEvent = {
          event: eventName,
          run_id: String(parsed.run_id ?? runId),
          thread_id: String(parsed.thread_id ?? ""),
          created_at:
            typeof parsed.created_at === "string"
              ? parsed.created_at
              : undefined,
          sequence:
            typeof parsed.sequence === "number" ? parsed.sequence : undefined,
          payload: parsed,
        };

        handlers.onEvent(streamEvent);

        if (
          eventName === "run_completed" ||
          eventName === "run_failed" ||
          eventName === "review_required"
        ) {
          terminalEventSeen = true;
          eventSource.close();
        }
      } catch {
        handlers.onError(`No se pudo parsear el evento ${eventName}`);
      }
    });
  };

  if (handlers.onOpen) {
    eventSource.onopen = () => {
      handlers.onOpen?.();
    };
  }

  eventSource.onerror = () => {
    if (terminalEventSeen) {
      return;
    }
    handlers.onError("La conexión SSE del copiloto falló o se cerró.");
    eventSource.close();
  };

  handleNamedEvent("run_started");
  handleNamedEvent("intent_classified");
  handleNamedEvent("agent_decision");
  handleNamedEvent("tool_called");
  handleNamedEvent("tool_result");
  handleNamedEvent("documents_selected");
  handleNamedEvent("retrieval_progress");
  handleNamedEvent("patch_proposed");
  handleNamedEvent("review_required");
  handleNamedEvent("patch_applied");
  handleNamedEvent("review_resolved");
  handleNamedEvent("response_chunk");
  handleNamedEvent("run_completed");
  handleNamedEvent("run_failed");

  return () => {
    eventSource.close();
  };
}
