import { FormEvent, useState } from "react";

import {
  CopilotPanelController,
  useCopilotPanelController,
} from "@/features/copilotDebug/useCopilotPanelController";

type CopilotDebugPanelProps = {
  encounterId: number;
  controller?: CopilotPanelController;
};

export default function CopilotDebugPanel({
  encounterId,
  controller,
}: CopilotDebugPanelProps) {
  const internalController = useCopilotPanelController(encounterId);
  const [message, setMessage] = useState(
    "Hazme un resumen breve del encounter actual"
  );
  const [reviewComment, setReviewComment] = useState("");
  const activeController = controller ?? internalController;
  const {
    state,
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
    reset,
    sendMessage,
    submitPatchReview,
  } = activeController;

  const handleInitSession = async () => {
    await ensureSession();
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(message);
  };

  const handleReview = async (decision: "approve" | "reject") => {
    if (!pendingPatch) {
      return;
    }
    await submitPatchReview(decision, reviewComment.trim() || undefined);
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
            Init session
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

      {state.lastError && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {state.lastError}
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
        {pendingPatch ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-700">
              <div>
                <span className="font-medium">patch_id:</span>{" "}
                {pendingPatch.patch_id}
              </div>
              <div>
                <span className="font-medium">target_document_id:</span>{" "}
                {pendingPatch.target_document_id}
              </div>
              <div>
                <span className="font-medium">target_document_title:</span>{" "}
                {pendingPatch.target_document_title ?? "—"}
              </div>
              <div>
                <span className="font-medium">base_version:</span>{" "}
                {pendingPatch.base_version}
              </div>
              <div>
                <span className="font-medium">operation_type:</span>{" "}
                {pendingPatch.operation_type}
              </div>
            </div>
            <div className="text-xs text-slate-700">
              <span className="font-medium">rationale:</span>{" "}
              {pendingPatch.rationale ?? "—"}
            </div>
            <div className="text-xs text-slate-700">
              <span className="font-medium">target_selection_reason:</span>{" "}
              {pendingPatch.target_selection_reason ?? "—"}
            </div>
            <div>
              <div className="text-xs font-medium text-slate-700 mb-2">
                before_preview
              </div>
              <pre className="max-h-40 overflow-auto rounded border bg-slate-50 p-3 text-[11px] whitespace-pre-wrap text-slate-800">
                {pendingPatch.before_preview ?? "—"}
              </pre>
            </div>
            <div>
              <div className="text-xs font-medium text-slate-700 mb-2">
                after_preview
              </div>
              <pre className="max-h-40 overflow-auto rounded border bg-slate-50 p-3 text-[11px] whitespace-pre-wrap text-slate-800">
                {pendingPatch.after_preview ?? "—"}
              </pre>
            </div>
            <div>
              <div className="text-xs font-medium text-slate-700 mb-2">
                document_preview_after
              </div>
              <pre className="max-h-48 overflow-auto rounded border bg-slate-50 p-3 text-[11px] whitespace-pre-wrap text-slate-800">
                {pendingPatch.document_preview_after ?? pendingPatch.content_preview}
              </pre>
            </div>
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
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleReview("approve")}
                className="px-3 py-2 text-sm rounded bg-green-700 text-white hover:bg-green-600"
              >
                Approve
              </button>
              <button
                type="button"
                onClick={() => void handleReview("reject")}
                className="px-3 py-2 text-sm rounded bg-red-700 text-white hover:bg-red-600"
              >
                Reject
              </button>
            </div>
          </>
        ) : (
          <div className="text-xs text-slate-500">
            No hay patch pendiente para este run.
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
          {searchQueryFromRun && (
            <div className="mt-2 text-[11px] text-slate-500">
              search_query: {searchQueryFromRun}
            </div>
          )}
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
