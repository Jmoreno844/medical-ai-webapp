import { useEffect, useRef, useState } from "react";

import { FileEdit, Loader2 } from "lucide-react";

interface PatchGeneratingCardProps {
  doctorSummary: string | null;
}

/**
 * Shown in the chat while the AI is generating patch proposals.
 * Uses the same border style as PatchReviewCard so the doctor sees a consistent
 * card shape from the moment generation starts until review is ready.
 *
 * If `doctorSummary` is provided (from the set_edit_plan tool_result event) it
 * plays a typewriter animation below the header to give the doctor a plain-language
 * preview of what the AI is about to change.
 */
export default function PatchGeneratingCard({
  doctorSummary,
}: PatchGeneratingCardProps) {
  const [displayed, setDisplayed] = useState("");
  const posRef = useRef(0);

  useEffect(() => {
    if (!doctorSummary) {
      posRef.current = 0;
      setDisplayed("");
      return;
    }
    posRef.current = 0;
    const timer = setInterval(() => {
      posRef.current += 1;
      setDisplayed(doctorSummary.slice(0, posRef.current));
      if (posRef.current >= doctorSummary.length) clearInterval(timer);
    }, 12);
    return () => clearInterval(timer);
  }, [doctorSummary]);

  return (
    <div className="mt-2 mr-2 rounded-lg border border-blue-100 bg-white shadow-sm">
      <div className="flex items-center gap-2 px-3 py-2">
        <FileEdit className="h-3.5 w-3.5 shrink-0 text-blue-500" />
        <span className="flex-1 truncate text-xs text-slate-600">
          Generando cambios al documento…
        </span>
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-slate-400" />
      </div>
      {displayed && (
        <div className="border-t border-slate-100 px-3 py-2 text-xs leading-relaxed text-slate-600">
          {displayed}
        </div>
      )}
    </div>
  );
}
