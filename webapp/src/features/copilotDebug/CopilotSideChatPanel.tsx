import { FormEvent, useState } from "react";

import { Button } from "@/commons/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/commons/components/ui/card";
import { ScrollArea } from "@/commons/components/ui/scroll-area";
import { CopilotPanelController } from "@/features/copilotDebug/useCopilotPanelController";

type CopilotSideChatPanelProps = {
  controller: CopilotPanelController;
};

export default function CopilotSideChatPanel({
  controller,
}: CopilotSideChatPanelProps) {
  const [message, setMessage] = useState("Hazme un resumen breve del encounter actual");
  const [reviewComment, setReviewComment] = useState("");
  const {
    state,
    chatMessages,
    pendingPatch,
    ensureSession,
    syncRunStatus,
    sendMessage,
    submitPatchReview,
  } = controller;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendMessage(message);
    setMessage("");
  };

  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden">
      <CardHeader className="space-y-2 border-b px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">Copilot</CardTitle>
            <p className="text-xs text-slate-600">
              Chat lateral interno para validar el flujo del copiloto.
            </p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => void ensureSession()}>
              Init
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void syncRunStatus()}
              disabled={!state.runId}
            >
              Refresh
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
          <span>status: {state.status}</span>
          <span>run: {state.runId ?? "—"}</span>
          <span>thread: {state.threadId ?? "—"}</span>
          <span>{state.isStreaming ? "streaming" : "idle"}</span>
        </div>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col gap-4 p-0">
        <ScrollArea className="min-h-0 flex-1 px-4 py-4">
          <div className="space-y-3">
            {chatMessages.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                Aun no hay mensajes. Puedes iniciar sesion y enviar una pregunta o instruccion.
              </div>
            ) : (
              chatMessages.map((messageItem) => (
                <div
                  key={messageItem.id}
                  className={[
                    "rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap",
                    messageItem.role === "user"
                      ? "ml-8 border-slate-900 bg-slate-900 text-white"
                      : messageItem.role === "assistant"
                        ? "mr-4 border-slate-200 bg-white text-slate-800"
                        : "mr-10 border-amber-200 bg-amber-50 text-amber-900",
                  ].join(" ")}
                >
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-wide opacity-70">
                    {messageItem.role}
                  </div>
                  {messageItem.content}
                </div>
              ))
            )}

            {state.isStreaming && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
                El copiloto esta procesando el run...
              </div>
            )}

            {pendingPatch && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 space-y-3">
                <div>
                  <div className="text-[11px] font-medium uppercase tracking-wide text-amber-700">
                    Review required
                  </div>
                  <div className="mt-1 font-medium">
                    {pendingPatch.target_document_title ??
                      `Documento ${pendingPatch.target_document_id}`}
                  </div>
                  <div className="mt-1 text-xs text-amber-800">
                    {pendingPatch.rationale ?? "Patch pendiente de revision humana."}
                  </div>
                </div>
                <div className="grid gap-2 text-xs md:grid-cols-2">
                  <div>
                    <div className="mb-1 font-medium">Before</div>
                    <pre className="max-h-32 overflow-auto rounded border border-amber-200 bg-white p-2 whitespace-pre-wrap">
                      {pendingPatch.before_preview ?? "—"}
                    </pre>
                  </div>
                  <div>
                    <div className="mb-1 font-medium">After</div>
                    <pre className="max-h-32 overflow-auto rounded border border-amber-200 bg-white p-2 whitespace-pre-wrap">
                      {pendingPatch.after_preview ??
                        pendingPatch.document_preview_after ??
                        pendingPatch.content_preview}
                    </pre>
                  </div>
                </div>
                <textarea
                  value={reviewComment}
                  onChange={(event) => setReviewComment(event.target.value)}
                  rows={2}
                  placeholder="Comentario opcional de review"
                  className="w-full rounded-md border border-amber-200 bg-white p-2 text-sm"
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    className="bg-green-700 text-white hover:bg-green-600"
                    onClick={() => void submitPatchReview("approve", reviewComment)}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => void submitPatchReview("reject", reviewComment)}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            )}

            {state.lastError && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {state.lastError}
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="border-t bg-slate-50 p-4">
          <form onSubmit={handleSubmit} className="space-y-2">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              rows={3}
              className="w-full rounded-md border bg-white p-3 text-sm"
              placeholder="Escribe una pregunta o instruccion para el copiloto"
            />
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] text-slate-500">
                {state.finalResponse ? "Ultima respuesta recibida." : "Sin respuesta final aun."}
              </div>
              <Button type="submit" disabled={!message.trim()}>
                Send
              </Button>
            </div>
          </form>
        </div>
      </CardContent>
    </Card>
  );
}
