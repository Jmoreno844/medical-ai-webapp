import { createChildLogger } from "@/lib/logger";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";
import {
  hasMeaningfulDocumentChange,
  sanitizeDocumentContentForSave,
  sendKeepaliveDocumentSave,
} from "@/workspace/utils/documentSave";

/**
 * A lightweight module-level registry that lets any mounted TextArea editor
 * expose a force-save function to the chat submission path.
 *
 * Usage:
 *   Editor mounts   → registerForceSave(docId, asyncSaveFn)
 *   Editor unmounts → the returned cleanup removes the entry
 *   Chat submits    → await flushDirtyDrafts([docId, ...])
 */

type SaveFn = (force?: boolean) => Promise<void>;

const _registry: Record<string, SaveFn> = {};
const log = createChildLogger("forceSaveRegistry");

export function registerForceSave(documentId: string, fn: SaveFn): () => void {
  _registry[documentId] = fn;
  return () => {
    if (_registry[documentId] === fn) {
      delete _registry[documentId];
    }
  };
}

/**
 * Flush all provided document IDs whose editors are currently mounted.
 * Calls each registered save function with force=true and awaits completion.
 * Documents without a registered editor are silently skipped — their content_markdown
 * will be excluded from the workspace index because isDirty will remain true.
 */
export async function flushDirtyDrafts(documentIds: string[]): Promise<void> {
  const withEditor = documentIds.filter((id) => Boolean(_registry[id]));
  const noEditor = documentIds.filter((id) => !_registry[id]);
  if (noEditor.length > 0) {
    // These docs have isDirty=true but no mounted editor, so they won't be
    // saved here. buildWorkspaceIndex will exclude content_markdown for them,
    // forcing the agent to call read_document on turn 1.
    log.warn("[forceSaveRegistry] dirty docs skipped — no editor mounted", {
      documentIds: noEditor,
    });
  }
  const pending = withEditor.map((id) => _registry[id](true));
  await Promise.allSettled(pending);
}

export function getDirtyDraftDocumentIds(): string[] {
  const draftState = useDocumentDraftStore.getState();
  return Object.entries(draftState.draftsByDocumentId)
    .filter(([, draft]) => draft?.isDirty)
    .map(([documentId]) => documentId);
}

export async function flushAllDirtyDrafts(): Promise<void> {
  const dirtyDocumentIds = getDirtyDraftDocumentIds();
  if (dirtyDocumentIds.length === 0) {
    return;
  }

  await flushDirtyDrafts(dirtyDocumentIds);
}

export function flushDirtyDraftsWithKeepalive(): void {
  const draftState = useDocumentDraftStore.getState();
  const snapshotState = useDocumentSnapshotStore.getState();

  for (const [documentId, draft] of Object.entries(draftState.draftsByDocumentId)) {
    if (!draft?.isDirty || typeof draft.localUnsavedContent !== "string") {
      continue;
    }

    const snapshot = snapshotState.getSnapshot(documentId);
    const sanitizedContent = sanitizeDocumentContentForSave(
      draft.localUnsavedContent,
    );

    if (!hasMeaningfulDocumentChange(snapshot?.contentMarkdown, sanitizedContent)) {
      continue;
    }

    const started = sendKeepaliveDocumentSave(documentId, sanitizedContent);
    if (started) {
      log.debug("[forceSaveRegistry] started keepalive save", { documentId });
    }
  }
}
