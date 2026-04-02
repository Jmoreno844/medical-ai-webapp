import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useCopilotDebug } from "@/features/copilotDebug/useCopilotDebug";
import {
  CopilotChatMessage,
  CopilotMessageRequest,
  CopilotPatchResponse,
} from "@/features/copilotDebug/types";
import { buildWorkspaceIndex } from "@/workspace/builders/workspaceIndex";
import { applyCopilotPatchToWorkspace } from "@/workspace/adapters/applyCopilotPatchToWorkspace";
import { useAiSessionStore } from "@/workspace/stores/aiSessionStore";
import { usePatchStore } from "@/workspace/stores/patchStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { DocumentPatch } from "@/workspace/types";

type UseCopilotPanelControllerResult = {
  state: ReturnType<typeof useCopilotDebug>["state"];
  chatMessages: CopilotChatMessage[];
  workspaceIndex: ReturnType<typeof buildWorkspaceIndex>;
  effectiveSelectedDocumentIds: string[];
  selectedDocumentIdsFromRun: string[];
  readDocumentsFromRun: Array<Record<string, unknown>>;
  latestToolCalls: Array<Record<string, unknown>>;
  latestToolResults: Array<Record<string, unknown>>;
  searchQueryFromRun: string | null;
  pendingPatch: CopilotPatchResponse | null;
  readMode: ReturnType<typeof useAiSessionStore.getState>["readMode"];
  ensureSession: () => Promise<unknown>;
  syncRunStatus: () => Promise<unknown>;
  reset: () => void;
  sendMessage: (message: string) => Promise<unknown>;
  submitPatchReview: (
    decision: "approve" | "reject",
    comment?: string
  ) => Promise<unknown>;
};

function buildChatMessage(
  role: CopilotChatMessage["role"],
  content: string,
  runId?: string | null
): CopilotChatMessage {
  return {
    id: `${role}-${runId ?? "local"}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    createdAt: new Date().toISOString(),
    runId,
  };
}

export function useCopilotPanelController(
  encounterId: number
): UseCopilotPanelControllerResult {
  const syncWorkingSetFromWorkspace = useAiSessionStore(
    (state) => state.syncWorkingSetFromWorkspace
  );
  const workingSetDocumentIds = useAiSessionStore(
    (state) => state.workingSetDocumentIds
  );
  const selectedDocumentIds = useAiSessionStore(
    (state) => state.selectedDocumentIds
  );
  const readMode = useAiSessionStore((state) => state.readMode);
  const setPatch = usePatchStore((state) => state.setPatch);
  const setPreviewContent = usePatchStore((state) => state.setPreviewContent);
  const selectPatch = usePatchStore((state) => state.selectPatch);
  const clearPatches = usePatchStore((state) => state.clearPatches);
  useWorkspaceStore();
  usePatchStore();

  const { state, ensureSession, runMessage, syncRunStatus, submitReview, reset } =
    useCopilotDebug(encounterId);
  const [chatMessages, setChatMessages] = useState<CopilotChatMessage[]>([]);
  const lastAssistantResponseRef = useRef<string | null>(null);
  const lastReviewPatchIdRef = useRef<string | null>(null);

  const workspaceIndex = buildWorkspaceIndex();

  const effectiveSelectedDocumentIds =
    selectedDocumentIds.length > 0
      ? selectedDocumentIds
      : workingSetDocumentIds.length > 0
        ? workingSetDocumentIds
        : workspaceIndex.documents
            .filter((document) => document.isActive || document.isOpen)
            .map((document) => document.documentId);

  const latestDocumentsSelectedEvent = [...state.events]
    .reverse()
    .find((event) => event.event === "documents_selected");
  const latestRetrievalEvent = [...state.events]
    .reverse()
    .find((event) => event.event === "retrieval_progress");
  const latestToolCalls = state.events
    .filter((event) => event.event === "tool_called")
    .map((event) => event.payload);
  const latestToolResults = state.events
    .filter((event) => event.event === "tool_result")
    .map((event) => event.payload);

  const selectedDocumentIdsFromRun = Array.isArray(
    latestDocumentsSelectedEvent?.payload.selected_document_ids
  )
    ? latestDocumentsSelectedEvent.payload.selected_document_ids.map(String)
    : [];
  const readDocumentsFromRun = Array.isArray(
    latestRetrievalEvent?.payload.read_documents
  )
    ? latestRetrievalEvent.payload.read_documents
    : [];
  const searchQueryFromRun =
    typeof latestRetrievalEvent?.payload.search_query === "string"
      ? latestRetrievalEvent.payload.search_query
      : null;

  const pendingPatch = useMemo(
    () => state.patches.find((patch) => patch.status === "pending") ?? null,
    [state.patches]
  );

  useEffect(() => {
    clearPatches();
    state.patches.forEach((patch) => {
      const mappedPatch: DocumentPatch = {
        id: patch.patch_id,
        documentId: patch.target_document_id,
        documentVersionBase: patch.base_version,
        createdBy: "ai",
        operationType:
          patch.operation_type === "replace_span"
            ? "replace_range"
            : patch.operation_type === "insert_after_span"
              ? "append_text"
              : "replace_range",
        summary: patch.rationale ?? "Patch propuesto por el copiloto",
        rationale: patch.rationale ?? undefined,
        sourceContextDocumentIds: patch.source_context_document_ids,
        beforeContent: patch.before_preview ?? undefined,
        afterContent: patch.document_preview_after ?? patch.content_preview,
        status:
          patch.status === "approved"
            ? "accepted"
            : patch.status === "rejected"
              ? "rejected"
              : patch.status === "applied"
                ? "applied"
                : patch.status === "stale"
                  ? "stale"
                  : "pending",
        createdAt: patch.created_at,
      };
      setPatch(mappedPatch);
      setPreviewContent(
        patch.target_document_id,
        patch.status === "pending"
          ? patch.document_preview_after ?? patch.content_preview
          : null
      );
    });

    if (pendingPatch) {
      selectPatch(pendingPatch.patch_id);
    } else {
      selectPatch(null);
    }
  }, [
    clearPatches,
    pendingPatch,
    selectPatch,
    setPatch,
    setPreviewContent,
    state.patches,
  ]);

  useEffect(() => {
    if (
      state.finalResponse &&
      state.finalResponse !== lastAssistantResponseRef.current
    ) {
      setChatMessages((current) => [
        ...current,
        buildChatMessage("assistant", state.finalResponse!, state.runId),
      ]);
      lastAssistantResponseRef.current = state.finalResponse;
    }
  }, [state.finalResponse, state.runId]);

  useEffect(() => {
    if (
      pendingPatch &&
      pendingPatch.patch_id !== lastReviewPatchIdRef.current
    ) {
      setChatMessages((current) => [
        ...current,
        buildChatMessage(
          "system",
          `Patch pendiente para ${pendingPatch.target_document_title ?? `documento ${pendingPatch.target_document_id}`}. Requiere review humana.`,
          state.runId
        ),
      ]);
      lastReviewPatchIdRef.current = pendingPatch.patch_id;
    }
    if (!pendingPatch) {
      lastReviewPatchIdRef.current = null;
    }
  }, [pendingPatch, state.runId]);

  const sendMessage = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) {
        return null;
      }

      syncWorkingSetFromWorkspace();
      const currentWorkspaceIndex = buildWorkspaceIndex();
      const aiSessionState = useAiSessionStore.getState();
      const currentSelectedDocumentIds =
        aiSessionState.selectedDocumentIds.length > 0
          ? aiSessionState.selectedDocumentIds
          : aiSessionState.workingSetDocumentIds.length > 0
            ? aiSessionState.workingSetDocumentIds
            : currentWorkspaceIndex.documents
                .filter((document) => document.isActive || document.isOpen)
                .map((document) => document.documentId);

      setChatMessages((current) => [
        ...current,
        buildChatMessage("user", trimmed, state.runId),
      ]);

      lastAssistantResponseRef.current = null;

      const payload: CopilotMessageRequest = {
        encounter_id: encounterId,
        user_message: trimmed,
        workspace_index: currentWorkspaceIndex,
        active_document_id: currentWorkspaceIndex.activeDocumentId,
        selected_document_ids: currentSelectedDocumentIds,
      };
      return runMessage(payload);
    },
    [encounterId, runMessage, state.runId, syncWorkingSetFromWorkspace]
  );

  const submitPatchReview = useCallback(
    async (decision: "approve" | "reject", comment?: string) => {
      if (!pendingPatch) {
        return null;
      }

      const currentWorkspaceIndex = buildWorkspaceIndex();
      const currentDocument = currentWorkspaceIndex.documents.find(
        (document) => document.documentId === pendingPatch.target_document_id
      );
      const run = await submitReview(
        pendingPatch.patch_id,
        decision,
        comment?.trim() || undefined,
        currentDocument?.version
      );

      if (
        decision === "approve" &&
        run?.applied_document_id &&
        typeof run.applied_content === "string"
      ) {
        applyCopilotPatchToWorkspace({
          documentId: run.applied_document_id,
          content: run.applied_content,
          baseVersion: pendingPatch.base_version,
          appliedVersion: run.applied_version,
          appliedPatchId: run.applied_patch_id,
        });
      }

      setChatMessages((current) => [
        ...current,
        buildChatMessage(
          "system",
          decision === "approve"
            ? "Patch aprobado."
            : "Patch rechazado.",
          run?.run_id ?? state.runId
        ),
      ]);

      return run;
    },
    [pendingPatch, state.runId, submitReview]
  );

  const wrappedReset = useCallback(() => {
    lastAssistantResponseRef.current = null;
    lastReviewPatchIdRef.current = null;
    setChatMessages([]);
    reset();
  }, [reset]);

  return {
    state,
    chatMessages,
    workspaceIndex,
    effectiveSelectedDocumentIds,
    selectedDocumentIdsFromRun,
    readDocumentsFromRun,
    latestToolCalls,
    latestToolResults,
    searchQueryFromRun,
    pendingPatch,
    readMode,
    ensureSession,
    syncRunStatus,
    reset: wrappedReset,
    sendMessage,
    submitPatchReview,
  };
}

export type CopilotPanelController = UseCopilotPanelControllerResult;
