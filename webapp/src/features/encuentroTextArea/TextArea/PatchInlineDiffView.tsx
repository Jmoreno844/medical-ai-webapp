import React, { useCallback, useEffect, useRef } from "react";
import {
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";
import { CopilotPatchResponse } from "@/features/copilotChat/types";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PatchInlineDiffViewProps {
  content: string;
  patches: CopilotPatchResponse[];
  /** The patch set that owns these patches — needed for scroll-to-selected. */
  patchSetId: string;
  onDecision: (patchId: string, decision: "approve" | "reject") => void;
}

type TextChunk = { type: "text"; text: string; key: string };
type PatchChunk = { type: "patch"; patch: CopilotPatchResponse; key: string };
type Chunk = TextChunk | PatchChunk;

// ---------------------------------------------------------------------------
// Chunk builder
// ---------------------------------------------------------------------------

function buildChunks(
  content: string,
  patches: CopilotPatchResponse[],
): Chunk[] {
  const resolved = [...patches]
    .filter((p) => p.resolvedRange != null)
    .sort((a, b) => a.resolvedRange!.start - b.resolvedRange!.start);

  const chunks: Chunk[] = [];
  let cursor = 0;

  for (const patch of resolved) {
    const { start, end } = patch.resolvedRange!;
    if (start > cursor) {
      chunks.push({
        type: "text",
        text: content.slice(cursor, start),
        key: `text-${cursor}`,
      });
    }
    chunks.push({ type: "patch", patch, key: `patch-${patch.id}` });
    cursor = Math.max(cursor, end);
  }

  if (cursor < content.length) {
    chunks.push({
      type: "text",
      text: content.slice(cursor),
      key: "text-tail",
    });
  }

  return chunks;
}

// ---------------------------------------------------------------------------
// Individual patch inline component
// ---------------------------------------------------------------------------

interface InlinePatchChunkProps {
  patch: CopilotPatchResponse;
  onDecision: (patchId: string, decision: "approve" | "reject") => void;
}

function InlinePatchChunk({ patch, onDecision }: InlinePatchChunkProps) {
  const selectedPatchId = usePatchSetStore((s) => s.selectedPatchId);
  const setSelectedPatch = usePatchSetStore((s) => s.setSelectedPatch);
  const isSelected = selectedPatchId === patch.id;
  const chunkRef = useRef<HTMLSpanElement>(null);

  // Scroll into view when this patch is selected (e.g. from the chat card).
  useEffect(() => {
    if (isSelected && chunkRef.current) {
      chunkRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [isSelected]);

  const handleSelect = useCallback(
    () => setSelectedPatch(patch.id),
    [patch.id, setSelectedPatch],
  );

  // ---- conflicted -----------------------------------------------------------
  if (patch.status === "conflicted") {
    return (
      <span
        ref={chunkRef}
        className="inline-flex items-center gap-1 bg-yellow-100 text-yellow-800 border border-yellow-300 rounded px-1 mx-0.5 text-sm"
        title="Este cambio tiene conflictos y no puede aplicarse automáticamente"
      >
        <AlertTriangle className="inline h-3 w-3 shrink-0" />
        {patch.oldText}
      </span>
    );
  }

  // ---- accepted ------------------------------------------------------------
  if (patch.status === "accepted") {
    return (
      <span ref={chunkRef} className="bg-green-50 text-green-900 rounded-sm">
        {patch.newText ?? ""}
      </span>
    );
  }

  // ---- rejected ------------------------------------------------------------
  if (patch.status === "rejected") {
    return (
      <span
        ref={chunkRef}
        className="text-gray-400 line-through decoration-gray-300"
      >
        {patch.oldText}
      </span>
    );
  }

  // ---- applied / stale — show as plain text --------------------------------
  if (patch.status === "applied" || patch.status === "stale") {
    return <span ref={chunkRef}>{patch.newText ?? patch.oldText}</span>;
  }

  // ---- pending: full inline diff with approve/reject buttons ---------------

  // For insert operations the anchor text is preserved exactly — nothing is
  // removed. Showing oldText in red would falsely imply the anchor is deleted.
  // Instead show the anchor as neutral context and only the inserted content
  // in green. We derive the inserted-only content from newText by stripping
  // the repeated anchor (insert_after: newText = oldText + inserted;
  //                         insert_before: newText = inserted + oldText).
  const isInsertAfter =
    patch.type === "insert_after" || patch.type === "insert_after_span";
  const isInsertBefore = patch.type === "insert_before";
  const isInsert = isInsertAfter || isInsertBefore;

  const insertedOnly: string | null = isInsert
    ? isInsertAfter && patch.newText.startsWith(patch.oldText)
      ? patch.newText.slice(patch.oldText.length)
      : isInsertBefore && patch.newText.endsWith(patch.oldText)
        ? patch.newText.slice(0, patch.newText.length - patch.oldText.length)
        : patch.newText // fallback: show full newText in green
    : null;

  return (
    <span
      ref={chunkRef}
      className={`inline cursor-pointer rounded-sm transition-shadow ${
        isSelected
          ? "ring-2 ring-indigo-400 ring-offset-1"
          : "hover:ring-1 hover:ring-indigo-200"
      }`}
      onClick={handleSelect}
      title={patch.rationale ?? undefined}
    >
      {isInsert ? (
        // Insert: anchor is context (no colour), only new content is green.
        isInsertBefore ? (
          <>
            <span className="bg-green-100 text-green-900">{insertedOnly}</span>
            <span>{patch.oldText}</span>
          </>
        ) : (
          <>
            <span>{patch.oldText}</span>
            <span className="bg-green-100 text-green-900">{insertedOnly}</span>
          </>
        )
      ) : (
        <>
          {/* Old text — red + strikethrough */}
          {patch.oldText && (
            <span className="bg-red-100 text-red-800 line-through decoration-red-400">
              {patch.oldText}
            </span>
          )}
          {/* New text — green */}
          {patch.newText && (
            <span className="bg-green-100 text-green-900">{patch.newText}</span>
          )}
        </>
      )}
      {/* Inline approve / reject buttons */}
      <span className="inline-flex items-center gap-0.5 ml-1 align-middle">
        <button
          className="inline-flex items-center justify-center w-5 h-5 rounded bg-green-600 hover:bg-green-700 text-white transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            onDecision(patch.id, "approve");
          }}
          title="Aprobar cambio"
          type="button"
        >
          <Check className="h-3 w-3" />
        </button>
        <button
          className="inline-flex items-center justify-center w-5 h-5 rounded bg-rose-500 hover:bg-rose-600 text-white transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            onDecision(patch.id, "reject");
          }}
          title="Rechazar cambio"
          type="button"
        >
          <X className="h-3 w-3" />
        </button>
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const PatchInlineDiffView: React.FC<PatchInlineDiffViewProps> = ({
  content,
  patches,
  onDecision,
}) => {
  const selectedPatchId = usePatchSetStore((s) => s.selectedPatchId);
  const setSelectedPatch = usePatchSetStore((s) => s.setSelectedPatch);

  const chunks = buildChunks(content, patches);

  // Patches that couldn't be located in the document (no resolvedRange and not conflicted).
  const unresolved = patches.filter(
    (p) => p.resolvedRange == null && p.status !== "conflicted",
  );
  const conflicted = patches.filter((p) => p.status === "conflicted");

  // Navigation among pending resolved patches.
  const pendingResolved = patches.filter(
    (p) => p.status === "pending" && p.resolvedRange != null,
  );
  const currentNavIdx = selectedPatchId
    ? pendingResolved.findIndex((p) => p.id === selectedPatchId)
    : -1;

  const goPrev = useCallback(() => {
    if (pendingResolved.length === 0) return;
    const idx =
      currentNavIdx <= 0 ? pendingResolved.length - 1 : currentNavIdx - 1;
    setSelectedPatch(pendingResolved[idx].id);
  }, [currentNavIdx, pendingResolved, setSelectedPatch]);

  const goNext = useCallback(() => {
    if (pendingResolved.length === 0) return;
    const idx =
      currentNavIdx === -1 || currentNavIdx >= pendingResolved.length - 1
        ? 0
        : currentNavIdx + 1;
    setSelectedPatch(pendingResolved[idx].id);
  }, [currentNavIdx, pendingResolved, setSelectedPatch]);

  const showNavBar = pendingResolved.length >= 3;
  const navLabel =
    currentNavIdx === -1
      ? `${pendingResolved.length} pendientes`
      : `${currentNavIdx + 1} / ${pendingResolved.length}`;

  return (
    <div className="flex flex-col h-full">
      {/* Navigation bar — only when there are 3 or more pending patches */}
      {showNavBar && (
        <div className="flex items-center justify-between px-4 py-2 bg-indigo-50 border-b border-indigo-100 shrink-0">
          <span className="text-sm font-medium text-indigo-700">
            {pendingResolved.length} cambio
            {pendingResolved.length !== 1 ? "s" : ""} pendiente
            {pendingResolved.length !== 1 ? "s" : ""}
          </span>
          <div className="flex items-center gap-2 text-sm text-indigo-700">
            <button
              className="p-1 rounded hover:bg-indigo-100 disabled:opacity-40 transition-colors"
              onClick={goPrev}
              type="button"
              title="Cambio anterior"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="tabular-nums text-xs">{navLabel}</span>
            <button
              className="p-1 rounded hover:bg-indigo-100 disabled:opacity-40 transition-colors"
              onClick={goNext}
              type="button"
              title="Cambio siguiente"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Conflict warning */}
      {conflicted.length > 0 && (
        <div className="px-4 py-2 bg-yellow-50 border-b border-yellow-200 text-yellow-800 text-xs shrink-0">
          <AlertTriangle className="inline h-3 w-3 mr-1" />
          {conflicted.length} cambio{conflicted.length > 1 ? "s" : ""} con
          conflicto{conflicted.length > 1 ? "s" : ""} — no se puede
          {conflicted.length > 1 ? "n" : ""} aplicar automáticamente.
        </div>
      )}

      {/* Document with inline diffs */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="leading-relaxed text-base text-gray-900 whitespace-pre-wrap">
          {chunks.map((chunk) => {
            if (chunk.type === "text") {
              return (
                <React.Fragment key={chunk.key}>{chunk.text}</React.Fragment>
              );
            }
            return (
              <InlinePatchChunk
                key={chunk.key}
                patch={chunk.patch}
                onDecision={onDecision}
              />
            );
          })}
        </div>

        {/* Patches without a resolvable position — shown at the bottom */}
        {unresolved.length > 0 && (
          <div className="mt-6 border-t border-gray-200 pt-4">
            <p className="text-xs text-gray-500 mb-2">
              Cambios que no pudieron ubicarse en el documento:
            </p>
            <div className="space-y-2">
              {unresolved.map((patch) => (
                <div
                  key={patch.id}
                  className="text-xs bg-gray-50 border border-gray-200 rounded p-2"
                >
                  {patch.oldText && (
                    <div className="text-red-700 line-through">
                      {patch.oldText}
                    </div>
                  )}
                  {patch.newText && (
                    <div className="text-green-700">→ {patch.newText}</div>
                  )}
                  {patch.status === "pending" && (
                    <div className="flex gap-2 mt-1">
                      <button
                        className="px-2 py-0.5 rounded bg-green-600 text-white text-xs hover:bg-green-700"
                        onClick={() => onDecision(patch.id, "approve")}
                        type="button"
                      >
                        Aprobar
                      </button>
                      <button
                        className="px-2 py-0.5 rounded bg-rose-500 text-white text-xs hover:bg-rose-600"
                        onClick={() => onDecision(patch.id, "reject")}
                        type="button"
                      >
                        Rechazar
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
