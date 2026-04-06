import { useCallback, useRef } from "react";
import {
  acceptCopilotPatch,
  rejectCopilotPatch,
  finalizeCopilotPatchSetReview,
} from "@/features/copilotChat/api";
import { applyCopilotPatchToWorkspace } from "@/workspace/adapters/applyCopilotPatchToWorkspace";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { createChildLogger } from "@/lib/logger";

const log = createChildLogger("usePatchDecision");
const COPILOT_PATCH_REVIEW_FINALIZED_EVENT = "copilot:patch-review-finalized";

/**
 * Standalone hook for approving/rejecting individual patches.
 * Performs an optimistic store update, syncs authoritative state from the
 * backend, and **auto-finalizes** when the last patch is decided — so
 * the accepted changes are applied to the document immediately without
 * requiring a separate "Aplicar cambios" click.
 */
export function usePatchDecision() {
  const updatePatchStatus = usePatchSetStore((s) => s.updatePatchStatus);
  const addPatchSet = usePatchSetStore((s) => s.addPatchSet);
  const clearAll = usePatchSetStore((s) => s.clearAll);
  const finalizingRef = useRef(false);

  const submitDecision = useCallback(
    async (
      patchSetId: string,
      patchId: string,
      decision: "approve" | "reject",
    ) => {
      // Optimistic update so the UI responds immediately.
      updatePatchStatus(
        patchSetId,
        patchId,
        decision === "approve" ? "accepted" : "rejected",
      );
      try {
        const updated =
          decision === "approve"
            ? await acceptCopilotPatch(patchSetId, { patch_id: patchId })
            : await rejectCopilotPatch(patchSetId, { patch_id: patchId });
        // Overwrite the whole patch set with the authoritative server state.
        addPatchSet(updated);

        // Auto-finalize: if no pending patches remain, apply immediately.
        const hasPending = updated.patches.some((p) => p.status === "pending");
        log.debug("patch decision applied to store", {
          patchId,
          decision,
          hasPending,
          finalizing: finalizingRef.current,
        });
        if (!hasPending && !finalizingRef.current) {
          finalizingRef.current = true;
          try {
            log.debug("all patches decided — auto-finalizing", { patchSetId });
            const run = await finalizeCopilotPatchSetReview(patchSetId, {});
            const outcome: "applied" | "rejected" = updated.patches.some(
              (patch) => patch.status === "accepted",
            )
              ? "applied"
              : "rejected";
            if (
              run?.applied_document_id &&
              typeof run.applied_content === "string"
            ) {
              applyCopilotPatchToWorkspace({
                documentId: run.applied_document_id,
                content: run.applied_content,
                baseVersion: updated.base_version ?? 1,
                appliedVersion: run.applied_version,
              });
            }
            window.dispatchEvent(
              new CustomEvent(COPILOT_PATCH_REVIEW_FINALIZED_EVENT, {
                detail: {
                  patchSet: updated,
                  outcome,
                  patchSetId,
                },
              }),
            );
            log.debug("auto-finalize completed — dispatched bridge event", {
              patchSetId,
              outcome,
              runStatus: run?.status,
            });
            // Clear review state so the editor switches back to Lexical.
            clearAll();
          } catch (finalizeErr) {
            log.warn("auto-finalize failed — doctor can retry from chat", {
              error: finalizeErr,
            });
          } finally {
            finalizingRef.current = false;
          }
        }
      } catch (err) {
        // Roll back the optimistic update so the doctor can retry.
        updatePatchStatus(patchSetId, patchId, "pending");
        throw err;
      }
    },
    [updatePatchStatus, addPatchSet, clearAll],
  );

  return { submitDecision };
}
