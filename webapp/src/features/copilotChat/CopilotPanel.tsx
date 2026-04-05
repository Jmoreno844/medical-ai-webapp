import { useState } from "react";
import { Bug } from "lucide-react";

import CopilotDebugPanel from "@/features/copilotChat/CopilotDebugPanel";
import { useCopilotPanelController } from "@/features/copilotChat/useCopilotPanelController";
import ChatBody from "@/features/copilotChat/ChatBody";

type CopilotPanelProps = {
  encounterId: number;
};

export default function CopilotPanel({ encounterId }: CopilotPanelProps) {
  const controller = useCopilotPanelController(encounterId);
  const [showDebug, setShowDebug] = useState(false);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-slate-800">
            Asistente clínico
          </span>
        </div>
        <button
          type="button"
          title={showDebug ? "Volver al chat" : "Vista técnica"}
          onClick={() => setShowDebug((v) => !v)}
          className={[
            "rounded-md p-1.5 transition-colors",
            showDebug
              ? "bg-slate-200 text-slate-700"
              : "text-slate-400 hover:bg-slate-100 hover:text-slate-600",
          ].join(" ")}
          aria-pressed={showDebug}
        >
          <Bug className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      {showDebug ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <CopilotDebugPanel
            encounterId={encounterId}
            controller={controller}
          />
        </div>
      ) : (
        <ChatBody controller={controller} />
      )}
    </div>
  );
}
