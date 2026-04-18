import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createChildLogger } from "@/lib/logger";
import { useCopilotDebug } from "@/features/copilotChat/useCopilotDebug";
import {
  CopilotChatMessage,
  CopilotMessageRequest,
  CopilotPatchResponse,
  CopilotPatchSetResponse,
} from "@/features/copilotChat/types";
import { buildWorkspaceIndex } from "@/workspace/builders/workspaceIndex";
import { applyCopilotPatchToWorkspace } from "@/workspace/adapters/applyCopilotPatchToWorkspace";
import { useAiSessionStore } from "@/workspace/stores/aiSessionStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { flushDirtyDrafts } from "@/workspace/forceSaveRegistry";

const COPILOT_PATCH_REVIEW_FINALIZED_EVENT = "copilot:patch-review-finalized";

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
  /** True when set_edit_plan was called in the current run — patch generation is in progress. */
  isGeneratingPatch: boolean;
  /** Plain-language summary from set_edit_plan for the doctor, used for typewriter animation. */
  editPlanDoctorSummary: string | null;
  /** The active review card (waiting_review). Null once decided. */
  reviewPatchSet: CopilotPatchSetResponse | null;
  /** Resolved card kept visible after the review closes (applied or rejected). */
  resolvedPatchCard: {
    patchSet: CopilotPatchSetResponse;
    outcome: "applied" | "rejected";
  } | null;
  reviewPatches: CopilotPatchResponse[];
  selectedReviewPatchId: string | null;
  selectedReviewPatch: CopilotPatchResponse | null;
  pendingPatchCount: number;
  acceptedPatchCount: number;
  rejectedPatchCount: number;
  conflictedPatchCount: number;
  canFinalizeAccepted: boolean;
  canFinalizeRejected: boolean;
  canFinalizeConflicted: boolean;
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
  submitPatchDecisionById: (
    patchId: string,
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

function isAdministrativePatchReviewFinalResponse(content: string): boolean {
  return (
    content ===
      "El patch set del copiloto fue aprobado y aplicado al documento canonico." ||
    content ===
      "El patch set del copiloto fue rechazado. No se aplicaron cambios al documento canonico."
  );
}

export function useCopilotPanelController(
  encounterId: number,
): UseCopilotPanelControllerResult {
  const log = createChildLogger("CopilotController");
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
  const lastAgentIntentMsgRunIdRef = useRef<string | null>(null);
  const lastPatchUiSignatureRef = useRef<string>("");
  // Tracks patchSet IDs already pushed to chatMessages to avoid duplicate history cards.
  const resolvedPatchCardsInChatRef = useRef<Set<string>>(new Set());
  const [resolvedPatchCard, setResolvedPatchCard] = useState<{
    patchSet: CopilotPatchSetResponse;
    outcome: "applied" | "rejected";
  } | null>(null);
  const [isFinalizingReview, setIsFinalizingReview] = useState(false);
  const lastResolvedPatchSetIdRef = useRef<string | null>(null);

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

  // True only while the run is in-flight AND a propose_* or set_edit_plan tool has
  // been called. Once the run reaches completed/failed/waiting_review the card must
  // disappear — otherwise it reappears on every subsequent message because the old
  // events survive in state until the next runMessage resets them.
  const isGeneratingPatch = useMemo(
    () =>
      !isFinalizingReview &&
      !resolvedPatchCard &&
      (state.isStreaming || state.status === "waiting_review") &&
      state.events.some(
        (e) =>
          e.event === "tool_called" &&
          (e.payload.tool_name === "set_edit_plan" ||
            String(e.payload.tool_name ?? "").startsWith("propose_")),
      ),
    [
      isFinalizingReview,
      resolvedPatchCard,
      state.events,
      state.isStreaming,
      state.status,
    ],
  );

  // The agent intent message: what the AI says it will do before generating patches.
  // Built once per run from set_edit_plan doctor_summary or propose_* reasoning_summary.
  // Persisted as a real "assistant" chat bubble so it survives after the card disappears.
  const agentIntentMessage = useMemo(() => {
    const resultEvent = [...state.events]
      .reverse()
      .find(
        (e) =>
          e.event === "tool_result" && e.payload.tool_name === "set_edit_plan",
      );
    if (resultEvent) {
      const nested = resultEvent.payload.payload;
      if (typeof nested === "object" && nested !== null) {
        const summary = (nested as Record<string, unknown>).doctor_summary;
        if (typeof summary === "string" && summary.length > 0) return summary;
      }
    }
    const proposeEvent = state.events.find(
      (e) =>
        e.event === "tool_called" &&
        String(e.payload.tool_name ?? "").startsWith("propose_"),
    );
    if (!proposeEvent) return null;
    const reasoning = proposeEvent.payload.reasoning_summary;
    if (
      typeof reasoning === "string" &&
      reasoning.length > 0 &&
      reasoning !== "tool_call_requested"
    ) {
      return reasoning;
    }
    const toolName = String(proposeEvent.payload.tool_name ?? "");
    if (toolName === "propose_replace_span")
      return "Voy a reemplazar texto en el documento.";
    if (
      toolName === "propose_insert_after_span" ||
      toolName === "propose_insert_before"
    )
      return "Voy a insertar texto en el documento.";
    if (toolName === "propose_delete_span")
      return "Voy a eliminar texto del documento.";
    return "Preparando cambios al documento.";
  }, [state.events]);

  // Inject agentIntentMessage as a persistent assistant chat bubble the first time
  // it becomes available for this run. Using a ref guard ensures it fires at most
  // once per run.
  //
  // Skip injection when the agent already streamed a finalResponse — the planner
  // emits its intent as text (response_chunk) in the same turn as the propose_*
  // tool call. The finalResponse useEffect already injected that text as a bubble,
  // so injecting agentIntentMessage on top would duplicate it.
  useEffect(() => {
    if (!agentIntentMessage || !state.runId) return;
    if (lastAgentIntentMsgRunIdRef.current === state.runId) return;
    // Mark the ref regardless so we never attempt injection again for this run.
    lastAgentIntentMsgRunIdRef.current = state.runId;
    if (state.finalResponse) return;
    setChatMessages((current) => [
      ...current,
      buildChatMessage("assistant", agentIntentMessage, state.runId),
    ]);
  }, [agentIntentMessage, state.runId, state.finalResponse]);

  // editPlanDoctorSummary is now null — the card only shows the spinner.
  // The text lives permanently in chatMessages via the effect above.
  const editPlanDoctorSummary = null;

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

  // Read patch state from the Zustand store so that decisions made from the inline
  // editor (usePatchDecision) are immediately reflected in the chat panel.
  // The store is populated both by the controller's sync effect (from state.patchSets)
  // and by usePatchDecision when the doctor acts from the document editor.
  const storeActivePatchSetId = usePatchSetStore((s) => s.activePatchSetId);
  const storePatchSets = usePatchSetStore((s) => s.patchSets);

  // Only expose a reviewPatchSet while the run is actively waiting for human review.
  // Once the review is finalizing or already resolved, suppress the active card
  // immediately so we do not fall back to stale state.patchSets data and render a
  // phantom "Aceptar / Rechazar" card at the bottom of the chat.
  const reviewPatchSet = useMemo(() => {
    if (state.status !== "waiting_review") return null;
    if (isFinalizingReview || resolvedPatchCard) return null;
    if (storeActivePatchSetId) {
      return storePatchSets[storeActivePatchSetId] ?? null;
    }
    const localPatchSets = Object.values(storePatchSets);
    if (localPatchSets.length > 0) {
      return localPatchSets[0] ?? null;
    }
    return state.patchSets[0] ?? null;
  }, [
    isFinalizingReview,
    resolvedPatchCard,
    state.patchSets,
    state.status,
    storeActivePatchSetId,
    storePatchSets,
  ]);

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

  // "pending" = still needs a doctor decision.
  // "conflicted" = two patches overlap in the same document region; the backend
  //   marks them automatically and skips them in accept-all / reject-all calls.
  //   They do NOT block finalization (backend only checks for status="pending").
  //   Keep them separate so the UI can explain the situation instead of looping.
  const serverReviewPatchSet = useMemo(
    () => state.patchSets.find((ps) => ps.id === reviewPatchSet?.id) || null,
    [state.patchSets, reviewPatchSet],
  );

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
  const conflictedPatchCount = useMemo(
    () => reviewPatches.filter((patch) => patch.status === "conflicted").length,
    [reviewPatches],
  );

  const serverPendingPatchCount =
    serverReviewPatchSet?.patches.filter((p) => p.status === "pending")
      .length ?? pendingPatchCount;
  const serverAcceptedPatchCount =
    serverReviewPatchSet?.patches.filter((p) => p.status === "accepted")
      .length ?? acceptedPatchCount;
  const serverRejectedPatchCount =
    serverReviewPatchSet?.patches.filter((p) => p.status === "rejected")
      .length ?? rejectedPatchCount;
  const serverConflictedPatchCount =
    serverReviewPatchSet?.patches.filter((p) => p.status === "conflicted")
      .length ?? conflictedPatchCount;

  useEffect(() => {
    const signature = JSON.stringify({
      runId: state.runId,
      status: state.status,
      isStreaming: state.isStreaming,
      isGeneratingPatch,
      isFinalizingReview,
      storeActivePatchSetId,
      reviewPatchSetId: reviewPatchSet?.id ?? null,
      resolvedPatchSetId: resolvedPatchCard?.patchSet.id ?? null,
      patchSetCount: state.patchSets.length,
      pendingPatchCount: serverPendingPatchCount,
      acceptedPatchCount: serverAcceptedPatchCount,
      rejectedPatchCount: serverRejectedPatchCount,
      conflictedPatchCount: serverConflictedPatchCount,
      latestReviewResolvedSequence: latestReviewResolvedEvent?.sequence ?? null,
    });
    if (lastPatchUiSignatureRef.current === signature) {
      return;
    }
    lastPatchUiSignatureRef.current = signature;
    log.debug("[patch-ui-state]", JSON.parse(signature));
  }, [
    conflictedPatchCount,
    isFinalizingReview,
    isGeneratingPatch,
    latestReviewResolvedEvent?.sequence,
    log,
    resolvedPatchCard,
    reviewPatchSet,
    serverAcceptedPatchCount,
    serverConflictedPatchCount,
    serverPendingPatchCount,
    serverRejectedPatchCount,
    state.isStreaming,
    state.patchSets.length,
    state.runId,
    state.status,
    storeActivePatchSetId,
  ]);

  // canFinalizeAccepted: all decisions made, at least one accepted → apply button.
  const canFinalizeAccepted =
    !!reviewPatchSet &&
    serverPendingPatchCount === 0 &&
    serverAcceptedPatchCount > 0;
  // canFinalizeRejected: all decisions made, all rejected → close without applying.
  const canFinalizeRejected =
    !!reviewPatchSet &&
    serverPendingPatchCount === 0 &&
    serverAcceptedPatchCount === 0 &&
    serverRejectedPatchCount > 0;
  // canFinalizeConflicted: no pending patches remain but all are conflicted (none accepted/rejected).
  const canFinalizeConflicted =
    !!reviewPatchSet &&
    serverPendingPatchCount === 0 &&
    serverAcceptedPatchCount === 0 &&
    serverRejectedPatchCount === 0 &&
    serverConflictedPatchCount > 0;

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
      log.debug("[waiting-review:auto-refresh]", {
        runId: state.runId,
        reason: "waiting_review-without-patchsets",
      });
      void syncRunStatus();
    }
    if (state.status !== "waiting_review") {
      didAutoRefreshWaitingReviewRef.current = null;
    }
  }, [log, state.patchSets.length, state.runId, state.status, syncRunStatus]);

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
      // "Newer wins": don't overwrite fresher data that usePatchDecision already wrote.
      const isNewer =
        !existingPatchSet ||
        activePatchSet.updated_at >= existingPatchSet.updated_at;
      const shouldUpsertPatchSet =
        isNewer &&
        (!existingPatchSet ||
          existingPatchCount !== activePatchSet.patches.length ||
          existingPatchSet.updated_at !== activePatchSet.updated_at ||
          existingPatchSet.status !== activePatchSet.status);

      const nextPatchSets = shouldUpsertPatchSet
        ? {
            ...storeState.patchSets,
            [activePatchSet.id]: activePatchSet,
          }
        : storeState.patchSets;

      const allPatchesTerminal = activePatchSet.patches.every(
        (patch) => patch.status !== "pending",
      );

      const nextActivePatchSetId =
        allPatchesTerminal && storeState.activePatchSetId === null
          ? null
          : activePatchSet.id;

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
      const shouldSuppressAdministrativeFinalResponse =
        !!resolvedPatchCard &&
        isAdministrativePatchReviewFinalResponse(state.finalResponse);
      if (shouldSuppressAdministrativeFinalResponse) {
        lastAssistantResponseRef.current = state.finalResponse;
        return;
      }
      setChatMessages((current) => {
        const lastMessage =
          current.length > 0 ? current[current.length - 1] : null;
        if (
          lastMessage?.role === "assistant" &&
          lastMessage?.runId === state.runId &&
          !lastMessage?.patchCard
        ) {
          // Update the content of the existing streamed message
          const withoutLast = current.slice(0, current.length - 1);
          return [
            ...withoutLast,
            { ...lastMessage, content: state.finalResponse! },
          ];
        }
        // Otherwise append as a new message
        return [
          ...current,
          buildChatMessage("assistant", state.finalResponse!, state.runId),
        ];
      });
      lastAssistantResponseRef.current = state.finalResponse;
    }
  }, [resolvedPatchCard, state.finalResponse, state.runId]);

  // Track when a review_resolved event arrives so we can show the resolved card.
  useEffect(() => {
    if (!latestReviewResolvedEvent) return;
    const resolvedPatchSetId =
      typeof latestReviewResolvedEvent.payload.patch_set_id === "string"
        ? latestReviewResolvedEvent.payload.patch_set_id
        : null;
    if (!resolvedPatchSetId) return;
    if (lastResolvedPatchSetIdRef.current === resolvedPatchSetId) return;
    lastResolvedPatchSetIdRef.current = resolvedPatchSetId;
    // Find the patch set data — it may still be in the store.
    const storePatchSetsSnapshot = usePatchSetStore.getState().patchSets;
    const resolvedData =
      storePatchSetsSnapshot[resolvedPatchSetId] ??
      Object.values(storePatchSetsSnapshot)[0] ??
      null;
    if (!resolvedData) return;
    const decision = latestReviewResolvedEvent.payload.decision;
    const resolvedCardData = {
      patchSet: resolvedData,
      outcome: (decision === "approve" ? "applied" : "rejected") as
        | "applied"
        | "rejected",
    };
    setResolvedPatchCard(resolvedCardData);
    if (!resolvedPatchCardsInChatRef.current.has(resolvedPatchSetId)) {
      resolvedPatchCardsInChatRef.current.add(resolvedPatchSetId);
      setChatMessages((current) => [
        ...current,
        {
          ...buildChatMessage("assistant", "", state.runId),
          patchCard: resolvedCardData,
        },
      ]);
    }
  }, [latestReviewResolvedEvent]);

  useEffect(() => {
    const handlePatchedReviewFinalized = (event: Event) => {
      const customEvent = event as CustomEvent<{
        patchSet?: CopilotPatchSetResponse;
        outcome?: "applied" | "rejected" | "conflict";
        conflictType?: "concurrent_edit" | "bad_anchor" | null;
        patchSetId?: string;
      }>;
      const patchSet = customEvent.detail?.patchSet;
      const outcome = customEvent.detail?.outcome;
      if (!patchSet || !outcome) {
        return;
      }
      log.debug("[patch-review-finalized:event] received bridge event", {
        patchSetId: customEvent.detail?.patchSetId,
        outcome,
        conflictType: customEvent.detail?.conflictType,
      });
      lastResolvedPatchSetIdRef.current = patchSet.id;
      if (outcome === "conflict") {
        const conflictType = customEvent.detail?.conflictType;
        const conflictMessage =
          conflictType === "concurrent_edit"
            ? "No pude aplicar los cambios porque el documento fue editado mientras el agente trabajaba. Vuelve a intentarlo."
            : conflictType === "bad_anchor"
              ? "No pude aplicar los cambios porque el texto exacto que el agente quería modificar no se encontró. Intenta de nuevo con una instrucción más específica."
              : "No pude aplicar los cambios. Intenta de nuevo.";
        setChatMessages((current) => [
          ...current,
          buildChatMessage("assistant", conflictMessage, state.runId),
        ]);
        setIsFinalizingReview(false);
        return;
      }
      const resolvedCard = {
        patchSet,
        outcome: outcome as "applied" | "rejected",
      };
      setResolvedPatchCard(resolvedCard);
      if (!resolvedPatchCardsInChatRef.current.has(patchSet.id)) {
        resolvedPatchCardsInChatRef.current.add(patchSet.id);
        setChatMessages((current) => [
          ...current,
          {
            ...buildChatMessage("assistant", "", state.runId),
            patchCard: resolvedCard,
          },
        ]);
      }
      setIsFinalizingReview(false);
    };

    window.addEventListener(
      COPILOT_PATCH_REVIEW_FINALIZED_EVENT,
      handlePatchedReviewFinalized as EventListener,
    );
    return () => {
      window.removeEventListener(
        COPILOT_PATCH_REVIEW_FINALIZED_EVENT,
        handlePatchedReviewFinalized as EventListener,
      );
    };
  }, [log, state.runId]);

  const sendMessage = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) {
        return null;
      }

      const session = await ensureSession();

      // Force-save any dirty editor drafts before building the workspace index.
      // This guarantees the DB reflects exactly what the doctor sees right now,
      // so the agent's pre-seeded content_markdown and any base_hash used by
      // the patcher matches the canonical document version in Django.
      const draftState = useDocumentDraftStore.getState();
      const dirtyDocIds = Object.entries(draftState.draftsByDocumentId)
        .filter(([, draft]) => draft?.isDirty)
        .map(([id]) => id);
      log.debug("[sendMessage] dirty docs before flush", { dirtyDocIds });
      if (dirtyDocIds.length > 0) {
        await flushDirtyDrafts(dirtyDocIds);
        // Log post-flush state to detect docs that still have isDirty=true
        // because their editor was not mounted (no registered saveFn).
        const postFlushDraft = useDocumentDraftStore.getState();
        const stillDirty = Object.entries(postFlushDraft.draftsByDocumentId)
          .filter(([id, draft]) => draft?.isDirty && dirtyDocIds.includes(id))
          .map(([id]) => id);
        if (stillDirty.length > 0) {
          log.warn(
            "[sendMessage] docs still dirty after flush — editor not mounted or re-dirtified by a follow-up editor update; workspaceIndex will use content-equality check to decide pre-seed",
            { stillDirty },
          );
        } else {
          log.debug("[sendMessage] all dirty docs flushed successfully");
        }
      }

      // Capture which document IDs the doctor recently edited (before clearing
      // the flag). This is the set that will emit <user_edit_notices> to the agent.
      const recentlyEditedDocIds = Object.entries(draftState.draftsByDocumentId)
        .filter(([, draft]) => draft?.userEditedSinceLastCopilotTurn)
        .map(([id]) => id);

      syncWorkingSetFromWorkspace();
      const currentWorkspaceIndex = buildWorkspaceIndex();
      log.debug(
        "[sendMessage] workspace index pre-seed summary",
        currentWorkspaceIndex.documents.map((d) => ({
          id: d.documentId,
          title: d.title,
          aiWritable: d.aiWritable,
          hasDirtyDraft: d.hasDirtyDraft,
          hasContent: Boolean(d.contentMarkdown),
          contentLen: d.contentMarkdown?.length ?? 0,
          // If aiWritable but no content, pre-seed is excluded — agent must read_document.
          preSeedExcluded: d.aiWritable && !d.contentMarkdown,
        })),
      );
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

      // Clear the resolved card so isGeneratingPatch works correctly for the
      // new run. The permanent record is already in chatMessages as a patchCard.
      setResolvedPatchCard(null);

      const payload: CopilotMessageRequest = {
        encounter_id: encounterId,
        thread_id: session.thread_id,
        user_message: trimmed,
        workspace_index: currentWorkspaceIndex,
        active_document_id: currentWorkspaceIndex.activeDocumentId,
        selected_document_ids: currentSelectedDocumentIds,
      };
      const result = runMessage(payload);
      // Reset the "doctor edited since last turn" flags now that the agent
      // has been given the up-to-date context.
      if (recentlyEditedDocIds.length > 0) {
        useDocumentDraftStore
          .getState()
          .markCopilotTurnConsumed(recentlyEditedDocIds);
      }
      return result;
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

      return patchSet;
    },
    [
      reviewPatchSet,
      selectedReviewPatch,
      state.runId,
      submitPatchDecisionRequest,
    ],
  );

  /** Approve or reject a specific patch by ID, without requiring it to be
   *  currently selected. Used by PatchReviewCard per-patch buttons. */
  const submitPatchDecisionById = useCallback(
    async (
      patchId: string,
      decision: "approve" | "reject",
      comment?: string,
    ) => {
      if (!reviewPatchSet) {
        return null;
      }

      const patch = reviewPatches.find((p) => p.id === patchId);
      if (!patch) {
        return null;
      }

      const patchSet = await submitPatchDecisionRequest(
        reviewPatchSet.id,
        patchId,
        decision,
        comment?.trim() || undefined,
      );

      return patchSet;
    },
    [reviewPatchSet, reviewPatches, state.runId, submitPatchDecisionRequest],
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
      return patchSet;
    },
    [reviewPatchSet, state.runId, submitPatchSetDecisionRequest],
  );

  const finalizeReview = useCallback(
    async (comment?: string) => {
      if (!reviewPatchSet) {
        return null;
      }

      const authoritativePatchSet = serverReviewPatchSet ?? reviewPatchSet;
      const resolvedOutcome: "applied" | "rejected" =
        serverAcceptedPatchCount > 0 ? "applied" : "rejected";

      const currentWorkspaceIndex = buildWorkspaceIndex();
      const currentDocument = currentWorkspaceIndex.documents.find(
        (document) =>
          document.documentId === authoritativePatchSet.target_document_id,
      );

      log.debug("[finalizeReview] calling finalizePatchSetReview", {
        patchSetId: authoritativePatchSet.id,
        targetDocumentId: authoritativePatchSet.target_document_id,
        documentVersion: currentDocument?.version,
        resolvedOutcome,
      });

      let run;
      setIsFinalizingReview(true);
      try {
        try {
          run = await finalizePatchSetReview(
            authoritativePatchSet.id,
            comment?.trim() || undefined,
            currentDocument?.version,
          );
        } catch (err: unknown) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const e = err as any;
          if (
            e?.message?.includes("409") ||
            e?.status === 409 ||
            e?.toString()?.includes("409")
          ) {
            log.warn(
              "backend had pending patches during finalize (409 conflict). Retrying in 1s...",
            );
            // Reset autoFinalizeTriggeredRef temporarily to allow retry
            autoFinalizeTriggeredRef.current = null;
            setTimeout(() => {
              void finalizeReview(comment);
            }, 1000);
            return null;
          }
          throw err;
        }

        log.debug("[finalizeReview] response from backend", {
          runStatus: run?.status,
          appliedDocumentId: run?.applied_document_id,
          appliedVersion: run?.applied_version,
          hasAppliedContent: typeof run?.applied_content === "string",
          appliedContentLength: run?.applied_content?.length ?? 0,
        });

        // Don't depend exclusively on a later review_resolved SSE event to hide the
        // generating card. The finalize call already tells us the review finished.
        lastResolvedPatchSetIdRef.current = authoritativePatchSet.id;
        const resolvedCard = {
          patchSet: authoritativePatchSet,
          outcome: resolvedOutcome,
        };
        setResolvedPatchCard(resolvedCard);
        if (!resolvedPatchCardsInChatRef.current.has(authoritativePatchSet.id)) {
          resolvedPatchCardsInChatRef.current.add(authoritativePatchSet.id);
          setChatMessages((current) => [
            ...current,
            {
              ...buildChatMessage("assistant", "", state.runId),
              patchCard: resolvedCard,
            },
          ]);
        }
        log.debug("[finalizeReview] resolved patch card set optimistically", {
          patchSetId: authoritativePatchSet.id,
          outcome: resolvedOutcome,
        });

        if (
          run?.applied_document_id &&
          typeof run.applied_content === "string"
        ) {
          log.debug("[finalizeReview] applying patch to workspace", {
            documentId: run.applied_document_id,
          });
          applyCopilotPatchToWorkspace({
            documentId: run.applied_document_id,
            content: run.applied_content,
            baseVersion:
              authoritativePatchSet.base_version ?? currentDocument?.version ?? 1,
            appliedVersion: run.applied_version,
          });
        }

        return run;
      } catch (error) {
        log.error("[finalizeReview] failed", error);
        throw error;
      } finally {
        setIsFinalizingReview(false);
      }
    },
    [
      finalizePatchSetReview,
      log,
      reviewPatchSet,
      serverAcceptedPatchCount,
      serverReviewPatchSet,
      state.runId,
    ],
  );

  const wrappedReset = useCallback(() => {
    lastAssistantResponseRef.current = null;
    lastReviewPatchSetIdRef.current = null;
    lastResolvedPatchSetIdRef.current = null;
    lastPatchSetSyncSignatureRef.current = "";
    lastPatchUiSignatureRef.current = "";
    resolvedPatchCardsInChatRef.current = new Set();
    setSelectedReviewPatchId(null);
    setIsFinalizingReview(false);
    setResolvedPatchCard(null);
    setChatMessages([]);
    usePatchSetStore.setState({
      patchSets: {},
      activePatchSetId: null,
      selectedPatchId: null,
    });
    reset();
  }, [reset]);

  // Auto-finalize when all patches are decided (e.g. after accept-all / reject-all
  // from the chat card).  The inline-editor path handles auto-finalize in usePatchDecision.
  const autoFinalizeTriggeredRef = useRef<string | null>(null);
  useEffect(() => {
    const shouldFinalize =
      canFinalizeAccepted || canFinalizeRejected || canFinalizeConflicted;
    if (!shouldFinalize || !reviewPatchSet) return;
    // Prevent re-trigger for the same patch set.
    if (autoFinalizeTriggeredRef.current === reviewPatchSet.id) return;
    autoFinalizeTriggeredRef.current = reviewPatchSet.id;
    void finalizeReview();
  }, [
    canFinalizeAccepted,
    canFinalizeRejected,
    canFinalizeConflicted,
    reviewPatchSet,
    finalizeReview,
  ]);

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
    isGeneratingPatch,
    editPlanDoctorSummary,
    reviewPatchSet,
    resolvedPatchCard,
    reviewPatches,
    selectedReviewPatchId,
    selectedReviewPatch,
    pendingPatchCount,
    acceptedPatchCount,
    rejectedPatchCount,
    conflictedPatchCount,
    canFinalizeAccepted,
    canFinalizeRejected,
    canFinalizeConflicted,
    patchFlowError,
    readMode,
    ensureSession,
    syncRunStatus,
    reset: wrappedReset,
    sendMessage,
    selectReviewPatch: setSelectedReviewPatchId,
    submitPatchDecision,
    submitPatchDecisionById,
    submitPatchSetDecision,
    finalizeReview,
  };
}

export type CopilotPanelController = UseCopilotPanelControllerResult;
