import { useCallback, useEffect, useRef, useState } from "react";

import { createChildLogger } from "@/lib/logger";
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
} from "@/features/copilotChat/api";
import {
  CopilotDebugState,
  CopilotMessageRequest,
  CopilotRunResponse,
  CopilotStreamEvent,
} from "@/features/copilotChat/types";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";

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

const TERMINAL_STATUSES = new Set(["completed", "failed", "waiting_review"]);
const PATCH_SET_HYDRATION_RETRY_MS = 250;
const PATCH_SET_HYDRATION_MAX_ATTEMPTS = 5;

export function useCopilotDebug(encounterId: number) {
  const log = createChildLogger("CopilotDebug");
  const [state, setState] = useState<CopilotDebugState>(INITIAL_STATE);
  const closeStreamRef = useRef<(() => void) | null>(null);
  const patchSetHydrationRunRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
    };
  }, []);

  // Keep the workspace store in sync so the editor can show a lock overlay
  // while the agent is running. setCopilotRunning is stable (Zustand action)
  // so this effect only re-runs when isStreaming actually changes.
  const setCopilotRunning = useWorkspaceStore((s) => s.setCopilotRunning);
  useEffect(() => {
    setCopilotRunning(state.isStreaming);
    return () => {
      // On unmount clear the flag so the editor doesn't stay locked
      // if the copilot panel is closed mid-run.
      setCopilotRunning(false);
    };
  }, [state.isStreaming, setCopilotRunning]);

  const appendEvent = useCallback((event: CopilotStreamEvent) => {
    if (event.event !== "response_chunk") {
      log.debug("[stream:event]", {
        event: event.event,
        sequence: event.sequence,
        runId: event.run_id,
      });
    }
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
          ? event.payload.is_chunk
            ? (current.finalResponse || "") + event.payload.content
            : event.payload.content
          : current.finalResponse;

      return {
        ...current,
        status: nextStatus,
        finalResponse: nextFinalResponse,
        isStreaming: !TERMINAL_STATUSES.has(nextStatus),
        lastError:
          event.event === "run_failed" &&
          typeof event.payload.error === "string"
            ? event.payload.error
            : current.lastError,
        events: [...current.events, event],
      };
    });
  }, []);

  const hydratePatchSets = useCallback(
    async (runId: string, reason: string) => {
      patchSetHydrationRunRef.current = runId;

      for (
        let attempt = 1;
        attempt <= PATCH_SET_HYDRATION_MAX_ATTEMPTS;
        attempt += 1
      ) {
        if (patchSetHydrationRunRef.current !== runId) {
          return;
        }

        try {
          const patchSets = await listCopilotPatchSets(runId);
          log.debug("[patch-set-hydration]", {
            runId,
            reason,
            attempt,
            patchSetCount: patchSets.length,
          });

          if (patchSets.length > 0) {
            setState((current) => {
              if (current.runId !== runId) {
                return current;
              }

              return {
                ...current,
                patchSets,
                status:
                  current.status === "completed"
                    ? "waiting_review"
                    : current.status,
                lastError: null,
              };
            });
            return;
          }
        } catch (error) {
          log.warn("[patch-set-hydration:error]", {
            runId,
            reason,
            attempt,
            message: String(error),
          });
        }

        if (attempt < PATCH_SET_HYDRATION_MAX_ATTEMPTS) {
          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, PATCH_SET_HYDRATION_RETRY_MS);
          });
        }
      }
    },
    [log],
  );

  const openStream = useCallback(
    (runId: string, afterSequence = 0) => {
      log.debug("[stream:open]", { runId, afterSequence });
      closeStreamRef.current?.();
      closeStreamRef.current = streamCopilotRun(runId, afterSequence, {
        onOpen: () => {
          log.debug("[stream:onOpen]", { runId, afterSequence });
          setState((current) => ({
            ...current,
            isStreaming: true,
            lastError: null,
          }));
        },
        onEvent: (event) => {
          appendEvent(event);
          if (
            event.event === "patch_proposed" ||
            event.event === "review_required"
          ) {
            void hydratePatchSets(event.run_id, event.event);
          }
        },
        onError: async (message) => {
          log.warn("[stream:onError]", { runId, afterSequence, message });
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
    [appendEvent, hydratePatchSets],
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
      // Show spinner immediately while the POST is in flight.
      setState((current) => ({
        ...current,
        isStreaming: true,
        lastError: null,
      }));
      let run;
      try {
        run = await sendCopilotMessage(payload);
      } catch (error) {
        setState((current) => ({
          ...current,
          isStreaming: false,
          status: "failed",
          lastError: String(error),
        }));
        throw error;
      }
      const patchSets = run.requires_human_review
        ? await listCopilotPatchSets(run.run_id)
        : [];
      // Keep isStreaming true — openStream's onOpen will manage it from here.
      setState({
        threadId: run.thread_id,
        runId: run.run_id,
        status: run.status,
        isStreaming: true,
        lastError: null,
        finalResponse: run.final_response ?? null,
        events: [],
        patchSets,
      });
      if (run.requires_human_review && patchSets.length === 0) {
        void hydratePatchSets(run.run_id, "runMessage");
      }
      openStream(run.run_id);
      return run;
    },
    [hydratePatchSets, openStream],
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
      comment?: string,
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
    [state.runId],
  );

  const submitPatchSetDecision = useCallback(
    async (
      patchSetId: string,
      decision: "approve" | "reject",
      comment?: string,
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
    [state.runId],
  );

  const finalizePatchSetReview = useCallback(
    async (patchSetId: string, comment?: string, documentVersion?: number) => {
      if (!state.runId) {
        return null;
      }

      const afterSequence = Math.max(
        0,
        ...state.events
          .map((event) => event.sequence ?? 0)
          .filter((sequence) => Number.isFinite(sequence)),
      );

      log.debug("[finalizePatchSetReview:start]", {
        runId: state.runId,
        patchSetId,
        afterSequence,
        documentVersion,
      });

      const run = await finalizeCopilotPatchSetReviewApi(patchSetId, {
        comment,
        document_version: documentVersion,
      });

      log.debug("[finalizePatchSetReview:response]", {
        runId: state.runId,
        patchSetId,
        status: run.status,
        appliedPatchSetId: run.applied_patch_set_id,
        appliedDocumentId: run.applied_document_id,
      });

      const patchSets = await listCopilotPatchSets(state.runId);
      log.debug("[finalizePatchSetReview:patchSets]", {
        runId: state.runId,
        patchSetId,
        patchSetCount: patchSets.length,
      });
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
    [log, openStream, state.events, state.runId],
  );

  const reset = useCallback(() => {
    closeStreamRef.current?.();
    closeStreamRef.current = null;
    patchSetHydrationRunRef.current = null;
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
