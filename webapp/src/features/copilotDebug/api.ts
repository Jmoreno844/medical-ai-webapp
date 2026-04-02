import axiosInstance from "@/commons/utils/axiosInstance";
import {
  CopilotMessageRequest,
  CopilotPatchResponse,
  CopilotRunResponse,
  CopilotSessionResponse,
  CopilotStreamEvent,
} from "@/features/copilotDebug/types";
import { WorkspaceIndex } from "@/workspace/types";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

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
      has_streaming_state: document.hasStreamingState,
      hidden_from_agent: document.hiddenFromAgent,
      pinned_for_agent: document.pinnedForAgent,
      excerpt: document.excerpt,
      short_summary: document.shortSummary,
      estimated_tokens: document.estimatedTokens,
      has_pending_patches: document.hasPendingPatches,
    })),
  };
}

export async function createCopilotSession(encounterId: number) {
  const response = await axiosInstance.post<CopilotSessionResponse>(
    "/api/copilot/sessions",
    {
      encounter_id: encounterId,
    }
  );

  return response.data;
}

export async function sendCopilotMessage(payload: CopilotMessageRequest) {
  const response = await axiosInstance.post<CopilotRunResponse>(
    "/api/copilot/messages",
    {
      encounter_id: payload.encounter_id,
      user_message: payload.user_message,
      workspace_index: serializeWorkspaceIndex(payload.workspace_index),
      active_document_id: payload.active_document_id,
      selected_document_ids: payload.selected_document_ids,
    }
  );

  return response.data;
}

export async function getCopilotRun(runId: string) {
  const response = await axiosInstance.get<CopilotRunResponse>(
    `/api/copilot/runs/${runId}`
  );

  return response.data;
}

export async function listCopilotPatches(runId: string) {
  const response = await axiosInstance.get<CopilotPatchResponse[]>(
    `/api/copilot/runs/${runId}/patches`
  );

  return response.data;
}

export async function reviewCopilotPatch(
  runId: string,
  payload: {
    patch_id: string;
    decision: "approve" | "reject";
    comment?: string | null;
    document_version?: number;
  }
) {
  const response = await axiosInstance.post<CopilotRunResponse>(
    `/api/copilot/runs/${runId}/review`,
    payload
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
  }
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
            typeof parsed.created_at === "string" ? parsed.created_at : undefined,
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
