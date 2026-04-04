import { useCallback, useEffect, useRef, useState } from "react";

import {
  acceptCopilotPatch,
  acceptAllCopilotPatches,
  createCopilotSession,
  finalizeCopilotPatchSetReview as finalizeCopilotPatchSetReviewApi,
  getCopilotRun,
  listCopilotPatchSets,
  rejectAllCopilotPatches,
  rejectCopilotPatch,
  sendCopilotMessage,
  streamCopilotRun,
} from "@/features/copilotDebug/api";
import {
  CopilotDebugState,
  CopilotMessageRequest,
  CopilotRunResponse,
  CopilotStreamEvent,
} from "@/features/copilotDebug/types";

const INITIAL_STATE: CopilotDebugState = {
  threadId: null,
  runId: null,
  status: "idle",
  isStreaming: false,
  lastError: null,
  finalResponse: null,
  events: [],
  patchSets: [],
};

const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function useCopilotDebug(encounterId: number) {
  const [state, setState] = useState<CopilotDebugState>(INITIAL_STATE);
  const closeStreamRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
    };
  }, []);

  const appendEvent = useCallback((event: CopilotStreamEvent) => {
    setState((current) => {
      const nextStatus =
        event.event === "run_completed"
          ? "completed"
          : event.event === "run_failed"
            ? "failed"
            : event.event === "review_required"
              ? "waiting_review"
          : current.status;

      const nextFinalResponse =
        event.event === "response_chunk" &&
        typeof event.payload.content === "string"
          ? event.payload.content
          : current.finalResponse;

      return {
        ...current,
        status: nextStatus,
        finalResponse: nextFinalResponse,
        isStreaming: !TERMINAL_STATUSES.has(nextStatus),
        lastError:
          event.event === "run_failed" && typeof event.payload.error === "string"
            ? event.payload.error
            : current.lastError,
        events: [...current.events, event],
      };
    });
  }, []);

  const openStream = useCallback(
    (runId: string, afterSequence = 0) => {
      closeStreamRef.current?.();
      closeStreamRef.current = streamCopilotRun(runId, afterSequence, {
        onOpen: () => {
          setState((current) => ({
            ...current,
            isStreaming: true,
            lastError: null,
          }));
        },
        onEvent: (event) => {
          appendEvent(event);
        },
        onError: async (message) => {
          setState((current) => ({
            ...current,
            isStreaming: false,
            lastError: message,
          }));

          try {
            const run = await getCopilotRun(runId);
            const patchSets = await listCopilotPatchSets(runId);
            setState((current) => ({
              ...current,
              status: run.status,
              finalResponse: run.final_response ?? current.finalResponse,
              patchSets,
            }));
          } catch {
            setState((current) => ({
              ...current,
              status: "failed",
            }));
          }
        },
      });
    },
    [appendEvent]
  );

  const ensureSession = useCallback(async () => {
    if (state.threadId) {
      return {
        thread_id: state.threadId,
        capability: "read_only" as const,
      };
    }
    const session = await createCopilotSession(encounterId);
    setState((current) => ({
      ...current,
      threadId: session.thread_id,
      status: current.status === "idle" ? "session_ready" : current.status,
      lastError: null,
    }));
    return session;
  }, [encounterId, state.threadId]);

  const runMessage = useCallback(
    async (payload: CopilotMessageRequest) => {
      const run = await sendCopilotMessage(payload);
      const patchSets =
        run.requires_human_review ? await listCopilotPatchSets(run.run_id) : [];
      setState({
        threadId: run.thread_id,
        runId: run.run_id,
        status: run.status,
        isStreaming: false,
        lastError: null,
        finalResponse: run.final_response ?? null,
        events: [],
        patchSets,
      });
      openStream(run.run_id);
      return run;
    },
    [openStream]
  );

  const syncRunStatus = useCallback(async () => {
    if (!state.runId) {
      return null;
    }

    const run: CopilotRunResponse = await getCopilotRun(state.runId);
    const patchSets = await listCopilotPatchSets(state.runId);
    setState((current) => ({
      ...current,
      status: run.status,
      finalResponse: run.final_response ?? current.finalResponse,
      lastError: null,
      patchSets,
    }));
    return run;
  }, [state.runId]);

  const submitPatchDecision = useCallback(
    async (
      patchSetId: string,
      patchId: string,
      decision: "approve" | "reject",
      comment?: string
    ) => {
      if (!state.runId) {
        return null;
      }

      const patchSet =
        decision === "approve"
          ? await acceptCopilotPatch(patchSetId, {
              patch_id: patchId,
              comment,
            })
          : await rejectCopilotPatch(patchSetId, {
              patch_id: patchId,
              comment,
            });

      const patchSets = await listCopilotPatchSets(state.runId);
      setState((current) => ({
        ...current,
        status: current.status,
        patchSets,
        lastError: null,
      }));
      return patchSet;
    },
    [state.runId]
  );

  const submitPatchSetDecision = useCallback(
    async (
      patchSetId: string,
      decision: "approve" | "reject",
      comment?: string
    ) => {
      if (!state.runId) {
        return null;
      }

      const patchSet =
        decision === "approve"
          ? await acceptAllCopilotPatches(patchSetId, { comment })
          : await rejectAllCopilotPatches(patchSetId, { comment });

      const patchSets = await listCopilotPatchSets(state.runId);
      setState((current) => ({
        ...current,
        patchSets,
        lastError: null,
      }));
      return patchSet;
    },
    [state.runId]
  );

  const finalizePatchSetReview = useCallback(
    async (
      patchSetId: string,
      comment?: string,
      documentVersion?: number
    ) => {
      if (!state.runId) {
        return null;
      }

      const afterSequence = Math.max(
        0,
        ...state.events
          .map((event) => event.sequence ?? 0)
          .filter((sequence) => Number.isFinite(sequence))
      );

      const run = await finalizeCopilotPatchSetReviewApi(patchSetId, {
        comment,
        document_version: documentVersion,
      });

      const patchSets = await listCopilotPatchSets(state.runId);
      setState((current) => ({
        ...current,
        status: run.status,
        finalResponse: run.final_response ?? current.finalResponse,
        patchSets,
        lastError: null,
      }));
      openStream(state.runId, afterSequence);
      return run;
    },
    [openStream, state.events, state.runId]
  );

  const reset = useCallback(() => {
    closeStreamRef.current?.();
    closeStreamRef.current = null;
    setState(INITIAL_STATE);
  }, []);

  return {
    state,
    ensureSession,
    runMessage,
    syncRunStatus,
    submitPatchDecision,
    submitPatchSetDecision,
    finalizePatchSetReview,
    reset,
  };
}
