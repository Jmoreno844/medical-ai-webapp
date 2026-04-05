import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Check,
  X,
  AlertTriangle,
} from "lucide-react";
import {
  CopilotPatchResponse,
  SECTION_DISPLAY_NAMES,
} from "@/features/copilotChat/types";
import { Button } from "@/commons/components/ui/button";

interface PatchSectionGroupProps {
  sectionKey: string;
  patches: CopilotPatchResponse[];
  onApprove: (patchId: string) => void;
  onReject: (patchId: string) => void;
}

function statusIcon(status: CopilotPatchResponse["status"]) {
  if (status === "accepted")
    return <Check className="h-3.5 w-3.5 text-green-500 shrink-0" />;
  if (status === "rejected")
    return <X className="h-3.5 w-3.5 text-red-400 shrink-0" />;
  if (status === "conflicted")
    return (
      <span title="Conflicto: no se puede aplicar automáticamente">
        <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
      </span>
    );
  return null;
}

export default function PatchSectionGroup({
  sectionKey,
  patches,
  onApprove,
  onReject,
}: PatchSectionGroupProps) {
  const [open, setOpen] = useState(true);

  const label = SECTION_DISPLAY_NAMES[sectionKey] ?? sectionKey;
  const pendingCount = patches.filter((p) => p.status === "pending").length;

  return (
    <div className="border border-slate-100 rounded-lg overflow-hidden">
      {/* Section header */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-slate-400 shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-slate-400 shrink-0" />
        )}
        <span className="flex-1 text-xs font-semibold text-slate-700 uppercase tracking-wide">
          {label}
        </span>
        {pendingCount > 0 && (
          <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
            {pendingCount} pendiente{pendingCount !== 1 ? "s" : ""}
          </span>
        )}
      </button>

      {/* Patch rows */}
      {open && (
        <ul className="divide-y divide-slate-100">
          {patches.map((patch) => (
            <li key={patch.id}>
              {/* Rationale row */}
              <div className="flex items-start gap-2 px-3 pt-2.5 pb-1">
                <span className="flex-1 text-xs leading-snug text-slate-700">
                  {patch.rationale ?? patch.type}
                </span>
                {statusIcon(patch.status)}
              </div>

              {/* Diff preview */}
              {(patch.oldText || patch.newText) && (
                <div className="mx-3 mb-2 rounded-md overflow-hidden border border-slate-100 text-[11px] font-mono leading-relaxed">
                  {patch.oldText && (
                    <div className="flex bg-red-50">
                      <span className="w-5 shrink-0 bg-red-100 text-red-400 text-center select-none border-r border-red-200">
                        −
                      </span>
                      <span className="px-2 py-1 text-red-800 whitespace-pre-wrap break-all line-through">
                        {patch.oldText}
                      </span>
                    </div>
                  )}
                  {patch.newText && (
                    <div className="flex bg-green-50">
                      <span className="w-5 shrink-0 bg-green-100 text-green-500 text-center select-none border-r border-green-200">
                        +
                      </span>
                      <span className="px-2 py-1 text-green-900 whitespace-pre-wrap break-all">
                        {patch.newText}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Action buttons — only for pending patches */}
              {patch.status === "pending" && (
                <div className="flex gap-1.5 px-3 pb-2.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 gap-1 px-2 text-[11px] text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700"
                    onClick={() => onReject(patch.id)}
                  >
                    <X className="h-3 w-3" />
                    Rechazar
                  </Button>
                  <Button
                    size="sm"
                    className="h-6 gap-1 px-2 text-[11px] bg-green-700 text-white hover:bg-green-600"
                    onClick={() => onApprove(patch.id)}
                  >
                    <Check className="h-3 w-3" />
                    Aprobar
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
