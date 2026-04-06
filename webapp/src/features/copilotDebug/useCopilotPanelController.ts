import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useCopilotDebug } from "@/features/copilotDebug/useCopilotDebug";
import {
  CopilotChatMessage,
  CopilotMessageRequest,
  CopilotPatchResponse,
  CopilotPatchSetResponse,
} from "@/features/copilotDebug/types";
import { buildWorkspaceIndex } from "@/workspace/builders/workspaceIndex";
import { applyCopilotPatchToWorkspace } from "@/workspace/adapters/applyCopilotPatchToWorkspace";
import { useAiSessionStore } from "@/workspace/stores/aiSessionStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";

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
  searchQueriesFromRun: string[];
  reviewPatchSet: CopilotPatchSetResponse | null;
  reviewPatches: CopilotPatchResponse[];
  selectedReviewPatchId: string | null;
  selectedReviewPatch: CopilotPatchResponse | null;
  pendingPatchCount: number;
  acceptedPatchCount: number;
  rejectedPatchCount: number;
  canFinalizeAccepted: boolean;
  canFinalizeRejected: boolean;
  patchFlowError: string | null;
  readMode: ReturnType<typeof useAiSessionStore.getState>["readMode"];
  ensureSession: () => Promise<unknown>;
  syncRunStatus: () => Promise<unknown>;
  reset: () => void;
  sendMessage: (message: string) => Promise<unknown>;
  selectReviewPatch: (patchId: string | null) => void;
  submitPatchDecision: (
    decision: "approve" | "reject",
    comment?: string,
  ) => Promise<unknown>;
  submitPatchSetDecision: (
    decision: "approve" | "reject",
    comment?: string,
  ) => Promise<unknown>;
  finalizeReview: (comment?: string) => Promise<unknown>;
};

function buildChatMessage(
  role: CopilotChatMessage["role"],
  content: string,
  runId?: string | null,
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
  encounterId: number,
): UseCopilotPanelControllerResult {
  const syncWorkingSetFromWorkspace = useAiSessionStore(
    (state) => state.syncWorkingSetFromWorkspace,
  );
  const workingSetDocumentIds = useAiSessionStore(
    (state) => state.workingSetDocumentIds,
  );
  const selectedDocumentIds = useAiSessionStore(
    (state) => state.selectedDocumentIds,
  );
  const readMode = useAiSessionStore((state) => state.readMode);
  useWorkspaceStore();

  const {
    state,
    ensureSession,
    runMessage,
    syncRunStatus,
    submitPatchDecision: submitPatchDecisionRequest,
    submitPatchSetDecision: submitPatchSetDecisionRequest,
    finalizePatchSetReview,
    reset,
  } = useCopilotDebug(encounterId);
  const [chatMessages, setChatMessages] = useState<CopilotChatMessage[]>([]);
  const [selectedReviewPatchId, setSelectedReviewPatchId] = useState<
    string | null
  >(null);
  const lastAssistantResponseRef = useRef<string | null>(null);
  const lastReviewPatchSetIdRef = useRef<string | null>(null);
  const didAutoRefreshWaitingReviewRef = useRef<string | null>(null);
  const lastPatchSetSyncSignatureRef = useRef<string>("");

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
    latestDocumentsSelectedEvent?.payload.selected_document_ids,
  )
    ? latestDocumentsSelectedEvent.payload.selected_document_ids.map(String)
    : [];
  const readDocumentsFromRun = Array.isArray(
    latestRetrievalEvent?.payload.read_documents,
  )
    ? latestRetrievalEvent.payload.read_documents
    : [];
  const searchQueryFromRun =
    typeof latestRetrievalEvent?.payload.search_query === "string"
      ? latestRetrievalEvent.payload.search_query
      : null;
  const searchQueriesFromRun = Array.isArray(
    latestRetrievalEvent?.payload.search_queries,
  )
    ? latestRetrievalEvent.payload.search_queries
        .map((value) => String(value))
        .filter((value) => value.length > 0)
    : searchQueryFromRun
      ? [searchQueryFromRun]
      : [];

  const latestPatchProposedEvent = [...state.events]
    .reverse()
    .find((event) => event.event === "patch_proposed");
  const latestReviewRequiredEvent = [...state.events]
    .reverse()
    .find((event) => event.event === "review_required");
  const latestReviewResolvedEvent = [...state.events]
    .reverse()
    .find((event) => event.event === "review_resolved");

  const eventDerivedPendingPatch = useMemo(() => {
    if (!latestPatchProposedEvent) {
      return null;
    }
    if (state.status !== "waiting_review") {
      return null;
    }

    const payload = latestPatchProposedEvent.payload;
    const patchId =
      typeof payload.patch_id === "string" ? payload.patch_id : null;
    const targetDocumentId =
      typeof payload.target_document_id === "string"
        ? payload.target_document_id
        : null;
    if (!patchId || !targetDocumentId) {
      return null;
    }

    const resolvedRangePayload =
      typeof payload.resolved_range === "object" &&
      payload.resolved_range !== null
        ? (payload.resolved_range as { start?: unknown; end?: unknown })
        : null;

    const resolvedRange =
      resolvedRangePayload &&
      typeof resolvedRangePayload.start === "number" &&
      typeof resolvedRangePayload.end === "number"
        ? { start: resolvedRangePayload.start, end: resolvedRangePayload.end }
        : typeof payload.resolved_start === "number"
          ? {
              start: payload.resolved_start,
              end:
                typeof payload.resolved_end === "number"
                  ? payload.resolved_end
                  : payload.resolved_start,
            }
          : null;

    return {
      id: patchId,
      patchSetId:
        typeof payload.patch_set_id === "string"
          ? payload.patch_set_id
          : "event-derived",
      documentId: targetDocumentId,
      type:
        typeof payload.patch_type === "string"
          ? payload.patch_type
          : typeof payload.operation_type === "string"
            ? payload.operation_type
            : "replace_span",
      anchor:
        typeof payload.anchor === "object" && payload.anchor !== null
          ? (payload.anchor as Record<string, unknown>)
          : {},
      oldText:
        typeof payload.old_text === "string"
          ? payload.old_text
          : typeof payload.before_preview === "string"
            ? payload.before_preview
            : "",
      newText:
        typeof payload.new_text === "string"
          ? payload.new_text
          : typeof payload.after_preview === "string"
            ? payload.after_preview
            : typeof payload.content_preview === "string"
              ? payload.content_preview
              : "",
      resolvedRange,
      orderIndex:
        typeof payload.order_index === "number" ? payload.order_index : 0,
      status: "pending",
      rationale:
        typeof payload.rationale === "string" ? payload.rationale : null,
      confidence:
        typeof payload.confidence === "number" ? payload.confidence : null,
    } satisfies CopilotPatchResponse;
  }, [latestPatchProposedEvent, state.status]);

  const reviewPatchSet = useMemo(() => {
    if (!Array.isArray(state.patchSets) || state.patchSets.length === 0) {
      return null;
    }
    return state.patchSets[0] ?? null;
  }, [state.patchSets]);

  const reviewPatches = useMemo(
    () => reviewPatchSet?.patches ?? [],
    [reviewPatchSet],
  );
  const selectedReviewPatch = useMemo(() => {
    if (reviewPatches.length === 0) {
      return eventDerivedPendingPatch;
    }
    if (selectedReviewPatchId) {
      const selectedPatch = reviewPatches.find(
        (patch) => patch.id === selectedReviewPatchId,
      );
      if (selectedPatch) {
        return selectedPatch;
      }
    }
    return (
      reviewPatches.find((patch) => patch.status === "pending") ??
      reviewPatches[0] ??
      eventDerivedPendingPatch
    );
  }, [eventDerivedPendingPatch, reviewPatches, selectedReviewPatchId]);

  const pendingPatchCount = useMemo(
    () => reviewPatches.filter((patch) => patch.status === "pending").length,
    [reviewPatches],
  );
  const acceptedPatchCount = useMemo(
    () => reviewPatches.filter((patch) => patch.status === "accepted").length,
    [reviewPatches],
  );
  const rejectedPatchCount = useMemo(
    () => reviewPatches.filter((patch) => patch.status === "rejected").length,
    [reviewPatches],
  );
  const canFinalizeAccepted =
    !!reviewPatchSet && pendingPatchCount === 0 && acceptedPatchCount > 0;
  const canFinalizeRejected =
    !!reviewPatchSet &&
    pendingPatchCount === 0 &&
    acceptedPatchCount === 0 &&
    rejectedPatchCount > 0;

  const patchSetSyncSignature = useMemo(
    () =>
      state.patchSets
        .map((patchSet) => {
          const patchSignature = patchSet.patches
            .map((patch) => `${patch.id}:${patch.status}`)
            .join(",");
          return `${patchSet.id}:${patchSet.status}:${patchSet.updated_at}:${patchSignature}`;
        })
        .join("|") || "empty",
    [state.patchSets],
  );

  const patchFlowError = useMemo(() => {
    if (state.lastError) {
      return state.lastError;
    }
    if (
      latestPatchProposedEvent &&
      state.status === "completed" &&
      !reviewPatchSet &&
      !latestReviewRequiredEvent &&
      !latestReviewResolvedEvent
    ) {
      return (
        "El run emitio patch_proposed pero termino en completed sin review_required " +
        "ni patch pendiente persistido. El flujo de edicion fue inconsistente."
      );
    }
    return null;
  }, [
    latestPatchProposedEvent,
    reviewPatchSet,
    state.lastError,
    state.status,
    latestReviewRequiredEvent,
    latestReviewResolvedEvent,
  ]);

  useEffect(() => {
    if (
      state.status === "waiting_review" &&
      state.runId &&
      state.patchSets.length === 0 &&
      didAutoRefreshWaitingReviewRef.current !== state.runId
    ) {
      didAutoRefreshWaitingReviewRef.current = state.runId;
      void syncRunStatus();
    }
    if (state.status !== "waiting_review") {
      didAutoRefreshWaitingReviewRef.current = null;
    }
  }, [state.patchSets.length, state.runId, state.status, syncRunStatus]);

  useEffect(() => {
    if (lastPatchSetSyncSignatureRef.current === patchSetSyncSignature) {
      return;
    }
    lastPatchSetSyncSignatureRef.current = patchSetSyncSignature;

    if (state.patchSets.length === 0) {
      usePatchSetStore.setState((storeState) => {
        const hasAnyPatchSet = Object.keys(storeState.patchSets).length > 0;
        if (
          !hasAnyPatchSet &&
          storeState.activePatchSetId === null &&
          storeState.selectedPatchId === null
        ) {
          return storeState;
        }
        return {
          ...storeState,
          patchSets: {},
          activePatchSetId: null,
          selectedPatchId: null,
        };
      });
      return;
    }

    const activePatchSet = state.patchSets[0];
    const patchIds = new Set(activePatchSet.patches.map((patch) => patch.id));
    const pendingInActiveSet = activePatchSet.patches.find(
      (patch) => patch.status === "pending",
    );
    const nextSelectedPatchId =
      selectedReviewPatchId && patchIds.has(selectedReviewPatchId)
        ? selectedReviewPatchId
        : (pendingInActiveSet?.id ?? activePatchSet.patches[0]?.id ?? null);

    usePatchSetStore.setState((storeState) => {
      const existingPatchSet = storeState.patchSets[activePatchSet.id];
      const existingPatchCount = existingPatchSet?.patches.length ?? -1;
      const shouldUpsertPatchSet =
        !existingPatchSet ||
        existingPatchCount !== activePatchSet.patches.length ||
        existingPatchSet.updated_at !== activePatchSet.updated_at ||
        existingPatchSet.status !== activePatchSet.status;

      const nextPatchSets = shouldUpsertPatchSet
        ? {
            ...storeState.patchSets,
            [activePatchSet.id]: activePatchSet,
          }
        : storeState.patchSets;

      const nextActivePatchSetId = activePatchSet.id;
      if (
        nextPatchSets === storeState.patchSets &&
        storeState.activePatchSetId === nextActivePatchSetId &&
        storeState.selectedPatchId === nextSelectedPatchId
      ) {
        return storeState;
      }

      return {
        ...storeState,
        patchSets: nextPatchSets,
        activePatchSetId: nextActivePatchSetId,
        selectedPatchId: nextSelectedPatchId,
      };
    });
    setSelectedReviewPatchId(nextSelectedPatchId);
  }, [patchSetSyncSignature, selectedReviewPatchId, state.patchSets]);

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
      reviewPatchSet &&
      reviewPatchSet.id !== lastReviewPatchSetIdRef.current
    ) {
      setChatMessages((current) => [
        ...current,
        buildChatMessage(
          "system",
          `Patch set pendiente para documento ${reviewPatchSet.target_document_id}. Requiere review humana.`,
          state.runId,
        ),
      ]);
      lastReviewPatchSetIdRef.current = reviewPatchSet.id;
    }
    if (!reviewPatchSet) {
      lastReviewPatchSetIdRef.current = null;
    }
  }, [reviewPatchSet, state.runId]);

  const sendMessage = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) {
        return null;
      }

      const session = await ensureSession();

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
        thread_id: session.thread_id,
        user_message: trimmed,
        workspace_index: currentWorkspaceIndex,
        active_document_id: currentWorkspaceIndex.activeDocumentId,
        selected_document_ids: currentSelectedDocumentIds,
      };
      return runMessage(payload);
    },
    [
      encounterId,
      ensureSession,
      runMessage,
      state.runId,
      syncWorkingSetFromWorkspace,
    ],
  );

  const submitPatchDecision = useCallback(
    async (decision: "approve" | "reject", comment?: string) => {
      if (!reviewPatchSet || !selectedReviewPatch) {
        return null;
      }

      const patchSet = await submitPatchDecisionRequest(
        reviewPatchSet.id,
        selectedReviewPatch.id,
        decision,
        comment?.trim() || undefined,
      );

      setChatMessages((current) => [
        ...current,
        buildChatMessage(
          "system",
          decision === "approve"
            ? `Patch ${selectedReviewPatch.orderIndex + 1} aprobado.`
            : `Patch ${selectedReviewPatch.orderIndex + 1} rechazado.`,
          state.runId,
        ),
      ]);

      return patchSet;
    },
    [
      reviewPatchSet,
      selectedReviewPatch,
      state.runId,
      submitPatchDecisionRequest,
    ],
  );

  const submitPatchSetDecision = useCallback(
    async (decision: "approve" | "reject", comment?: string) => {
      if (!reviewPatchSet) {
        return null;
      }

      const patchSet = await submitPatchSetDecisionRequest(
        reviewPatchSet.id,
        decision,
        comment?.trim() || undefined,
      );
      setChatMessages((current) => [
        ...current,
        buildChatMessage(
          "system",
          decision === "approve"
            ? "Todos los patches fueron aprobados."
            : "Todos los patches fueron rechazados.",
          state.runId,
        ),
      ]);
      return patchSet;
    },
    [reviewPatchSet, state.runId, submitPatchSetDecisionRequest],
  );

  const finalizeReview = useCallback(
    async (comment?: string) => {
      if (!reviewPatchSet) {
        return null;
      }

      const currentWorkspaceIndex = buildWorkspaceIndex();
      const currentDocument = currentWorkspaceIndex.documents.find(
        (document) => document.documentId === reviewPatchSet.target_document_id,
      );
      const run = await finalizePatchSetReview(
        reviewPatchSet.id,
        comment?.trim() || undefined,
        currentDocument?.version,
      );

      if (run?.applied_document_id && typeof run.applied_content === "string") {
        applyCopilotPatchToWorkspace({
          documentId: run.applied_document_id,
          content: run.applied_content,
          baseVersion:
            reviewPatchSet.base_version ?? currentDocument?.version ?? 1,
          appliedVersion: run.applied_version,
        });
      }

      setChatMessages((current) => [
        ...current,
        buildChatMessage(
          "system",
          acceptedPatchCount > 0
            ? "Cambios aplicados al documento."
            : "Revision cerrada sin aplicar cambios.",
          run?.run_id ?? state.runId,
        ),
      ]);

      return run;
    },
    [acceptedPatchCount, finalizePatchSetReview, reviewPatchSet, state.runId],
  );

  const wrappedReset = useCallback(() => {
    lastAssistantResponseRef.current = null;
    lastReviewPatchSetIdRef.current = null;
    lastPatchSetSyncSignatureRef.current = "";
    setSelectedReviewPatchId(null);
    setChatMessages([]);
    usePatchSetStore.setState({
      patchSets: {},
      activePatchSetId: null,
      selectedPatchId: null,
    });
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
    searchQueriesFromRun,
    reviewPatchSet,
    reviewPatches,
    selectedReviewPatchId,
    selectedReviewPatch,
    pendingPatchCount,
    acceptedPatchCount,
    rejectedPatchCount,
    canFinalizeAccepted,
    canFinalizeRejected,
    patchFlowError,
    readMode,
    ensureSession,
    syncRunStatus,
    reset: wrappedReset,
    sendMessage,
    selectReviewPatch: setSelectedReviewPatchId,
    submitPatchDecision,
    submitPatchSetDecision,
    finalizeReview,
  };
}

export type CopilotPanelController = UseCopilotPanelControllerResult;
