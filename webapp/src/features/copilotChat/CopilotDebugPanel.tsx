import { FormEvent, useState } from "react";

import {
  CopilotPanelController,
} from "@/features/copilotChat/useCopilotPanelController";

type CopilotDebugPanelProps = {
  encounterId?: number;
  controller: CopilotPanelController;
};

export default function CopilotDebugPanel({
  controller,
}: CopilotDebugPanelProps) {
  const [message, setMessage] = useState(
    "Hazme un resumen breve del encounter actual"
  );
  const [reviewComment, setReviewComment] = useState("");
  const activeController = controller;
  const {
    state,
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
    reset,
    sendMessage,
    selectReviewPatch,
    submitPatchDecision,
    submitPatchSetDecision,
    finalizeReview,
  } = activeController;

  const handleInitSession = async () => {
    await ensureSession();
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(message);
  };

  const handlePatchDecision = async (decision: "approve" | "reject") => {
    if (!selectedReviewPatch) {
      return;
    }
    await submitPatchDecision(decision, reviewComment.trim() || undefined);
    setReviewComment("");
  };

  const handlePatchSetDecision = async (decision: "approve" | "reject") => {
    if (!reviewPatchSet) {
      return;
    }
    await submitPatchSetDecision(decision, reviewComment.trim() || undefined);
    setReviewComment("");
  };

  const handleFinalizeReview = async () => {
    if (!reviewPatchSet) {
      return;
    }
    await finalizeReview(reviewComment.trim() || undefined);
    setReviewComment("");
  };

  return (
    <section className="border rounded-md bg-slate-50 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Copilot Debug Panel
          </h2>
          <p className="text-xs text-slate-600">
            Vertical slice interno para validar review y apply seguro del copiloto.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleInitSession}
            className="px-3 py-1.5 text-xs rounded border bg-white hover:bg-slate-100"
          >
            Init chat
          </button>
          <button
            type="button"
            onClick={() => void syncRunStatus()}
            disabled={!state.runId}
            className="px-3 py-1.5 text-xs rounded border bg-white hover:bg-slate-100 disabled:opacity-50"
          >
            Refresh run
          </button>
          <button
            type="button"
            onClick={reset}
            className="px-3 py-1.5 text-xs rounded border bg-white hover:bg-slate-100"
          >
            Reset
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <div className="rounded border bg-white p-3 space-y-1">
          <div>
            <span className="font-medium">thread_id:</span>{" "}
            {state.threadId ?? "—"}
          </div>
          <div>
            <span className="font-medium">run_id:</span> {state.runId ?? "—"}
          </div>
          <div>
            <span className="font-medium">status:</span> {state.status}
          </div>
          <div>
            <span className="font-medium">streaming:</span>{" "}
            {state.isStreaming ? "yes" : "no"}
          </div>
          <div>
            <span className="font-medium">readMode:</span> {readMode}
          </div>
        </div>

        <div className="rounded border bg-white p-3 space-y-1">
          <div>
            <span className="font-medium">encounterId:</span>{" "}
            {workspaceIndex.encounterId}
          </div>
          <div>
            <span className="font-medium">workspaceVersion:</span>{" "}
            {workspaceIndex.workspaceVersion.slice(0, 80)}
          </div>
          <div>
            <span className="font-medium">activeDocumentId:</span>{" "}
            {workspaceIndex.activeDocumentId ?? "—"}
          </div>
          <div>
            <span className="font-medium">documents:</span>{" "}
            {workspaceIndex.documents.length}
          </div>
          <div>
            <span className="font-medium">workingSet:</span>{" "}
            {effectiveSelectedDocumentIds.join(", ") || "—"}
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-2">
        <label className="block text-xs font-medium text-slate-700">
          Mensaje al copiloto
        </label>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={3}
          className="w-full rounded border p-3 text-sm bg-white"
        />
        <button
          type="submit"
          disabled={!message.trim()}
          className="px-3 py-2 text-sm rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
        >
          Send run
        </button>
      </form>

      {patchFlowError && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {patchFlowError}
        </div>
      )}

      <div className="rounded border bg-white p-3">
        <div className="text-xs font-medium text-slate-700 mb-2">
          Final response
        </div>
        <pre className="text-xs whitespace-pre-wrap text-slate-800">
          {state.finalResponse ?? "—"}
        </pre>
      </div>

      <div className="rounded border bg-white p-3 space-y-3">
        <div className="text-xs font-medium text-slate-700">
          Patch review
        </div>
        {reviewPatchSet ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-700">
              <div>
                <span className="font-medium">patch_set_id:</span>{" "}
                {reviewPatchSet.id}
              </div>
              <div>
                <span className="font-medium">target_document_id:</span>{" "}
                {reviewPatchSet.target_document_id}
              </div>
              <div>
                <span className="font-medium">status:</span>{" "}
                {reviewPatchSet.status}
              </div>
              <div>
                <span className="font-medium">patches:</span>{" "}
                {reviewPatches.length}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs text-slate-700">
              <div className="rounded border bg-slate-50 p-2">
                <span className="font-medium">pending:</span> {pendingPatchCount}
              </div>
              <div className="rounded border bg-green-50 p-2">
                <span className="font-medium">accepted:</span> {acceptedPatchCount}
              </div>
              <div className="rounded border bg-red-50 p-2">
                <span className="font-medium">rejected:</span> {rejectedPatchCount}
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-xs font-medium text-slate-700">
                Patches del set
              </div>
              <div className="space-y-2">
                {reviewPatches.map((patch) => {
                  const isSelected = patch.id === (selectedReviewPatchId ?? selectedReviewPatch?.id);
                  return (
                    <button
                      key={patch.id}
                      type="button"
                      onClick={() => selectReviewPatch(patch.id)}
                      className={[
                        "w-full rounded border px-3 py-2 text-left text-xs",
                        isSelected
                          ? "border-slate-900 bg-slate-100"
                          : "border-slate-200 bg-white hover:bg-slate-50",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">
                          Patch {patch.orderIndex + 1}
                        </span>
                        <span className="text-[11px] uppercase text-slate-500">
                          {patch.status}
                        </span>
                      </div>
                      <div className="mt-1 text-slate-600">
                        {patch.rationale ?? patch.type}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
            {selectedReviewPatch ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-700">
                  <div>
                    <span className="font-medium">patch_id:</span>{" "}
                    {selectedReviewPatch.id}
                  </div>
                  <div>
                    <span className="font-medium">resolved_range:</span>{" "}
                    {selectedReviewPatch.resolvedRange
                      ? `${selectedReviewPatch.resolvedRange.start}-${selectedReviewPatch.resolvedRange.end}`
                      : "—"}
                  </div>
                  <div>
                    <span className="font-medium">type:</span>{" "}
                    {selectedReviewPatch.type}
                  </div>
                  <div>
                    <span className="font-medium">order_index:</span>{" "}
                    {selectedReviewPatch.orderIndex}
                  </div>
                </div>
                <div className="text-xs text-slate-700">
                  <span className="font-medium">rationale:</span>{" "}
                  {selectedReviewPatch.rationale ?? "—"}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs font-medium text-red-700 mb-2">
                      old_text
                    </div>
                    <pre className="max-h-40 overflow-auto rounded border border-red-200 bg-red-50 p-3 text-[11px] whitespace-pre-wrap text-slate-800">
                      {selectedReviewPatch.oldText || "—"}
                    </pre>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-green-700 mb-2">
                      new_text
                    </div>
                    <pre className="max-h-40 overflow-auto rounded border border-green-200 bg-green-50 p-3 text-[11px] whitespace-pre-wrap text-slate-800">
                      {selectedReviewPatch.newText || "—"}
                    </pre>
                  </div>
                </div>
              </>
            ) : null}
            <div className="space-y-2">
              <label className="block text-xs font-medium text-slate-700">
                Review comment
              </label>
              <textarea
                value={reviewComment}
                onChange={(event) => setReviewComment(event.target.value)}
                rows={2}
                className="w-full rounded border p-3 text-sm bg-white"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handlePatchDecision("approve")}
                disabled={!selectedReviewPatch || selectedReviewPatch.status !== "pending"}
                className="px-3 py-2 text-sm rounded bg-green-700 text-white hover:bg-green-600"
              >
                Approve patch
              </button>
              <button
                type="button"
                onClick={() => void handlePatchDecision("reject")}
                disabled={!selectedReviewPatch || selectedReviewPatch.status !== "pending"}
                className="px-3 py-2 text-sm rounded bg-red-700 text-white hover:bg-red-600"
              >
                Reject patch
              </button>
              <button
                type="button"
                onClick={() => void handlePatchSetDecision("approve")}
                disabled={pendingPatchCount === 0}
                className="px-3 py-2 text-sm rounded border bg-white hover:bg-slate-100 disabled:opacity-50"
              >
                Accept all
              </button>
              <button
                type="button"
                onClick={() => void handlePatchSetDecision("reject")}
                disabled={pendingPatchCount === 0}
                className="px-3 py-2 text-sm rounded border bg-white hover:bg-slate-100 disabled:opacity-50"
              >
                Reject all
              </button>
              <button
                type="button"
                onClick={() => void handleFinalizeReview()}
                disabled={!canFinalizeAccepted && !canFinalizeRejected}
                className="px-3 py-2 text-sm rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {canFinalizeAccepted
                  ? "Apply accepted"
                  : canFinalizeRejected
                    ? "Finish rejection"
                    : "Finalize review"}
              </button>
            </div>
          </>
        ) : (
          <div className="text-xs text-slate-500">
            {patchFlowError
              ? "El flujo de edicion termino en un estado inconsistente; revisa los eventos del run."
              : "No hay patch pendiente para este run."}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded border bg-white p-3">
          <div className="text-xs font-medium text-slate-700 mb-2">
            Selected documents
          </div>
          <div className="text-xs text-slate-700">
            {selectedDocumentIdsFromRun.length > 0
              ? selectedDocumentIdsFromRun.join(", ")
              : "—"}
          </div>
        </div>
        <div className="rounded border bg-white p-3">
          <div className="text-xs font-medium text-slate-700 mb-2">
            Read documents
          </div>
          <div className="space-y-1 text-xs text-slate-700">
            {readDocumentsFromRun.length === 0 ? (
              <div>—</div>
            ) : (
              readDocumentsFromRun.map((document, index) => (
                <div key={`${String(document.document_id)}-${index}`}>
                  {String(document.title ?? document.document_id)}{" "}
                  {document.read_mode ? `(${String(document.read_mode)})` : ""}
                </div>
              ))
            )}
          </div>
          {searchQueriesFromRun.length > 0 ? (
            <div className="mt-2 text-[11px] text-slate-500">
              search_queries: {searchQueriesFromRun.join(", ")}
            </div>
          ) : searchQueryFromRun ? (
            <div className="mt-2 text-[11px] text-slate-500">
              search_query: {searchQueryFromRun}
            </div>
          ) : null}
        </div>
      </div>

      <div className="rounded border bg-white p-3">
          <div className="text-xs font-medium text-slate-700 mb-2">
            Stream events
          </div>
        <div className="space-y-2 max-h-72 overflow-auto">
          {state.events.length === 0 ? (
            <div className="text-xs text-slate-500">No events yet.</div>
          ) : (
            state.events.map((event, index) => (
              <div
                key={`${event.event}-${event.sequence ?? index}`}
                className="rounded border border-slate-200 p-2"
              >
                <div className="text-xs font-medium text-slate-800">
                  {event.event}
                </div>
                <pre className="text-[11px] whitespace-pre-wrap text-slate-600">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded border bg-white p-3">
          <div className="text-xs font-medium text-slate-700 mb-2">
            Tool calls
          </div>
          <div className="space-y-2 max-h-52 overflow-auto">
            {latestToolCalls.length === 0 ? (
              <div className="text-xs text-slate-500">No tool calls yet.</div>
            ) : (
              latestToolCalls.map((payload, index) => (
                <pre
                  key={`tool-call-${index}`}
                  className="rounded border border-slate-200 p-2 text-[11px] whitespace-pre-wrap text-slate-600"
                >
                  {JSON.stringify(payload, null, 2)}
                </pre>
              ))
            )}
          </div>
        </div>
        <div className="rounded border bg-white p-3">
          <div className="text-xs font-medium text-slate-700 mb-2">
            Tool results
          </div>
          <div className="space-y-2 max-h-52 overflow-auto">
            {latestToolResults.length === 0 ? (
              <div className="text-xs text-slate-500">No tool results yet.</div>
            ) : (
              latestToolResults.map((payload, index) => (
                <pre
                  key={`tool-result-${index}`}
                  className="rounded border border-slate-200 p-2 text-[11px] whitespace-pre-wrap text-slate-600"
                >
                  {JSON.stringify(payload, null, 2)}
                </pre>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
