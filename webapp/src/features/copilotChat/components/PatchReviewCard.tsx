import { FileEdit, AlertTriangle, Check, X } from "lucide-react";
import { Button } from "@/commons/components/ui/button";
import {
  CopilotPatchSetResponse,
  CopilotPatchResponse,
} from "@/features/copilotChat/types";

interface PatchReviewCardProps {
  patchSet: CopilotPatchSetResponse;
  patches: CopilotPatchResponse[];
  pendingCount: number;
  acceptedCount: number;
  rejectedCount: number;
  conflictedCount: number;
  onApproveAll: () => void;
  onRejectAll: () => void;
  /** Unused by this compact view but kept so the call site doesn't need to change */
  onApprovePatch: (patchId: string) => void;
  onRejectPatch: (patchId: string) => void;
  /** When set the card shows a resolved state instead of action buttons. */
  resolved?: "applied" | "rejected";
}

/**
 * Compact inline pill shown in the chat when the AI proposes changes.
 * Detailed per-patch review happens directly in the document editor.
 */
export default function PatchReviewCard({
  patchSet,
  patches,
  pendingCount,
  acceptedCount,
  conflictedCount,
  onApproveAll,
  onRejectAll,
  resolved,
}: PatchReviewCardProps) {
  const docTitle = patchSet.target_document_title ?? "Documento";
  const total = patches.length;
  const allDecided = pendingCount === 0;

  return (
    <div className="mt-2 mr-2 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <FileEdit className="h-3.5 w-3.5 shrink-0 text-blue-500" />

      {/* Title + conflict badge */}
      <span className="min-w-0 flex-1 truncate text-xs text-slate-700">
        {total} cambio{total !== 1 ? "s" : ""} en{" "}
        <span className="font-medium">{docTitle}</span>
      </span>

      {conflictedCount > 0 && !allDecided && !resolved && (
        <span className="flex shrink-0 items-center gap-0.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
          <AlertTriangle className="h-2.5 w-2.5" />
          {conflictedCount}
        </span>
      )}

      {/* Resolved state — replaces buttons with a static pill */}
      {resolved ? (
        resolved === "applied" ? (
          <span className="flex shrink-0 items-center gap-1 rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
            <Check className="h-3 w-3" />
            Aplicado
          </span>
        ) : (
          <span className="flex shrink-0 items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            <X className="h-3 w-3" />
            Rechazado
          </span>
        )
      ) : (
        <>
          {/* Progress counter */}
          <span className="shrink-0 text-xs font-medium tabular-nums text-slate-500">
            {acceptedCount}/{total}
          </span>

          {allDecided ? (
            <span className="shrink-0 text-xs text-slate-400">Aplicando…</span>
          ) : (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-6 shrink-0 gap-1 px-2 text-xs text-slate-600"
                onClick={onRejectAll}
                title="Rechazar todos"
              >
                <X className="h-3 w-3" />
                Rechazar
              </Button>
              <Button
                size="sm"
                className="h-6 shrink-0 gap-1 bg-green-700 px-2 text-xs text-white hover:bg-green-600"
                onClick={onApproveAll}
                title="Aceptar todos"
              >
                <Check className="h-3 w-3" />
                Aceptar
              </Button>
            </>
          )}
        </>
      )}
    </div>
  );
}
