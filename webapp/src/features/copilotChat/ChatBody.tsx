import { FormEvent, useEffect, useRef, useState } from "react";

import { ScrollArea } from "@/commons/components/ui/scroll-area";
import { CopilotPanelController } from "@/features/copilotChat/useCopilotPanelController";
import ChatMessageList from "@/features/copilotChat/components/ChatMessageList";
import StatusIndicator from "@/features/copilotChat/components/StatusIndicator";
import ChatInput from "@/features/copilotChat/components/ChatInput";
import PatchReviewCard from "@/features/copilotChat/components/PatchReviewCard";

type ChatBodyProps = {
  controller: CopilotPanelController;
};

export default function ChatBody({ controller }: ChatBodyProps) {
  const [message, setMessage] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const {
    state,
    chatMessages,
    reviewPatchSet,
    reviewPatches,
    pendingPatchCount,
    acceptedPatchCount,
    rejectedPatchCount,
    conflictedPatchCount,
    patchFlowError,
    ensureSession,
    sendMessage,
    submitPatchDecisionById,
    submitPatchSetDecision,
  } = controller;

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages.length, state.isStreaming]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!message.trim()) return;
    const text = message;
    setMessage("");
    // Ensure a session exists before first send
    await ensureSession();
    await sendMessage(text);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ScrollArea className="min-h-0 flex-1 px-4 py-4">
        <ChatMessageList messages={chatMessages} />

        {state.isStreaming && <StatusIndicator />}

        {/* Patch review card — grouped by section with per-patch approve/reject */}
        {reviewPatchSet && (
          <PatchReviewCard
            patchSet={reviewPatchSet}
            patches={reviewPatches}
            pendingCount={pendingPatchCount}
            acceptedCount={acceptedPatchCount}
            rejectedCount={rejectedPatchCount}
            conflictedCount={conflictedPatchCount}
            onApproveAll={async () => {
              await submitPatchSetDecision("approve");
            }}
            onRejectAll={async () => {
              await submitPatchSetDecision("reject");
            }}
            onApprovePatch={async (patchId) => {
              await submitPatchDecisionById(patchId, "approve");
            }}
            onRejectPatch={async (patchId) => {
              await submitPatchDecisionById(patchId, "reject");
            }}
          />
        )}

        {patchFlowError && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {patchFlowError}
          </div>
        )}

        <div ref={bottomRef} />
      </ScrollArea>

      <div className="shrink-0 border-t border-slate-100">
        <ChatInput
          value={message}
          onChange={setMessage}
          onSubmit={handleSubmit}
          disabled={state.isStreaming}
        />
      </div>
    </div>
  );
}
