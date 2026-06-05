import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import {
  flushAllDirtyDrafts,
  flushDirtyDrafts,
  flushDirtyDraftsWithKeepalive,
  registerForceSave,
} from "@/workspace/forceSaveRegistry";
import { useDocumentContext } from "../../../contexts/DocumentContext";
import { useContentContext } from "../../../contexts/ContentContext";
import { useGenerationContext } from "../../../contexts/GenerationContext";
import { useTranscriptionContext } from "../../../contexts/TranscriptionContext";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { usePatchSetStore } from "@/workspace/stores/patchSetStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { usePatchDecision } from "@/workspace/hooks/usePatchDecision";
import { logger } from "@/lib/logger";
import {
  getEmptyTiptapDoc,
  isTiptapJsonContent,
  medicalEditorExtensions,
} from "./tiptap/medicalEditor";
import {
  PatchReviewDecorationExtension,
  resolvePatchReviewPatches,
  setPatchReviewDecorations,
} from "./tiptap/patchReviewDecorations";
import SegmentedTranscriptionView from "./SegmentedTranscriptionView";
import SelectionBubbleMenu from "./SelectionBubbleMenu";
import { postClientAuditEvent } from "@/api/audit";

type EditorSnapshot = {
  markdown: string;
  json: Record<string, unknown> | null;
};

function normalizeEditorText(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}

const INITIAL_GENERATION_STATUS_CHUNK = "Iniciando generación de documento...";

function markdownLooksStructured(markdown: string): boolean {
  return /(^|\n)\s{0,3}#{1,6}\s+/.test(markdown) ||
    /(^|\n)\s*[-*+]\s+/.test(markdown) ||
    /(^|\n)\s*\d+\.\s+/.test(markdown) ||
    /\*\*[^*]+\*\*/.test(markdown);
}

function extractTiptapPlainText(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }

  const node = value as {
    type?: string;
    text?: string;
    content?: unknown[];
  };

  if (node.type === "text") {
    return node.text ?? "";
  }

  if (node.type === "hardBreak") {
    return "\n";
  }

  return (node.content ?? []).map(extractTiptapPlainText).join("");
}

function shouldPreferMarkdownOverJson(
  markdown: string,
  json: Record<string, unknown> | null,
): boolean {
  if (!json || !markdownLooksStructured(markdown)) {
    return false;
  }

  return normalizeEditorText(extractTiptapPlainText(json)) ===
    normalizeEditorText(markdown);
}

function readEditorSnapshot(editor: Editor): EditorSnapshot {
  return {
    markdown: editor.getMarkdown(),
    json: (editor.getJSON() as Record<string, unknown>) ?? null,
  };
}

const TextArea: React.FC = () => {
  const { activeDocument, activeDocumentId } = useDocumentContext();
  const {
    documentContent,
    documentContentJson,
    fetchError,
    isLoadingContent,
    contentLoadedSuccessfully,
    reloadContent,
    saveContent,
    editorRefreshTrigger,
    documentContentCache,
  } = useContentContext();
  const { generationStatus, retryGeneration, isGenerating } =
    useGenerationContext();
  const { transcriptionCompleteTimestamp } = useTranscriptionContext();
  const setDraftContent = useDocumentDraftStore((state) => state.setDraftContent);
  const derivedByDocumentId = useDocumentDerivedStore(
    (state) => state.derivedByDocumentId,
  );
  const activePatchSetId = usePatchSetStore((state) => state.activePatchSetId);
  const patchSets = usePatchSetStore((state) => state.patchSets);
  const selectedPatchId = usePatchSetStore((state) => state.selectedPatchId);
  const setSelectedPatch = usePatchSetStore((state) => state.setSelectedPatch);
  const isCopilotRunning = useWorkspaceStore((state) => state.isCopilotRunning);
  const { submitDecision } = usePatchDecision();

  const [generationSuccessDocumentId, setGenerationSuccessDocumentId] =
    useState<number | null>(null);
  const previousDocIdRef = useRef<number | null>(null);
  const previousRefreshTriggerRef = useRef(editorRefreshTrigger);
  const previousGenerationSnapshotRef = useRef<{
    documentId: number | null;
    isComplete: boolean;
  }>({
    documentId: null,
    isComplete: false,
  });
  const generationSuccessTimerRef = useRef<number | null>(null);
  const ignoreEditorUpdatesRef = useRef(true);
  const hasHydratedDocumentRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const saveInFlightRef = useRef(false);

  const handlePatchApprove = useCallback(
    (patchId: string) => {
      const patchSetId = usePatchSetStore.getState().activePatchSetId;
      if (!patchSetId) {
        return;
      }
      void submitDecision(patchSetId, patchId, "approve").catch((error) => {
        logger.error("[PATCH_REVIEW] Failed to approve patch", {
          patchSetId,
          patchId,
          error,
        });
      });
    },
    [submitDecision],
  );

  const handlePatchReject = useCallback(
    (patchId: string) => {
      const patchSetId = usePatchSetStore.getState().activePatchSetId;
      if (!patchSetId) {
        return;
      }
      void submitDecision(patchSetId, patchId, "reject").catch((error) => {
        logger.error("[PATCH_REVIEW] Failed to reject patch", {
          patchSetId,
          patchId,
          error,
        });
      });
    },
    [submitDecision],
  );

  const handleCopy = useCallback(() => {
    if (!activeDocumentId || !activeDocument) {
      return;
    }
    void postClientAuditEvent({
      action: "document.copied",
      encounter_id: Number(activeDocument.encounter_id),
      document_id: activeDocumentId,
    });
  }, [activeDocument, activeDocumentId]);

  const editorExtensions = useMemo(
    () => [
      ...medicalEditorExtensions,
      PatchReviewDecorationExtension.configure({
        onSelectPatch: (patchId) => {
          usePatchSetStore.getState().setSelectedPatch(patchId);
        },
        onApprovePatch: handlePatchApprove,
        onRejectPatch: handlePatchReject,
      }),
    ],
    [handlePatchApprove, handlePatchReject],
  );

  const editor = useEditor({
    immediatelyRender: false,
    shouldRerenderOnTransaction: false,
    extensions: editorExtensions,
    content: getEmptyTiptapDoc(),
    editable: false,
    editorProps: {
      attributes: {
        class:
          "h-full overflow-auto px-4 py-3 focus:outline-none leading-normal text-[15px] text-slate-800",
        spellcheck: "false",
      },
    },
  });

  const triggerEditorSave = useCallback(
    async (): Promise<void> => {
      if (
        !editor ||
        !activeDocumentId ||
        !editor.isEditable ||
        saveInFlightRef.current ||
        !hasHydratedDocumentRef.current
      ) {
        return;
      }

      const snapshot = readEditorSnapshot(editor);

      if (contentLoadedSuccessfully && snapshot.markdown.trim() === "") {
        logger.warn(
          "Skipped empty save because the document already has canonical content",
        );
        return;
      }

      try {
        saveInFlightRef.current = true;
        await saveContent(
          activeDocumentId,
          snapshot.markdown,
          snapshot.json,
        );
      } catch (error) {
        logger.error("[TIPTAP_SAVE] Failed to save document", {
          activeDocumentId,
          error,
        });
      } finally {
        saveInFlightRef.current = false;
      }
    },
    [activeDocumentId, contentLoadedSuccessfully, editor, saveContent],
  );

  const scheduleEditorSave = useCallback(() => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
    }

    saveTimerRef.current = window.setTimeout(() => {
      void triggerEditorSave();
      saveTimerRef.current = null;
    }, 1000);
  }, [triggerEditorSave]);

  const handleDraftChange = useCallback(
    (docId: number, content: string, contentJson: Record<string, unknown> | null) => {
      setDraftContent(String(docId), content, contentJson);
    },
    [setDraftContent],
  );

  useEffect(() => {
    if (
      activeDocument &&
      editorRefreshTrigger !== previousRefreshTriggerRef.current
    ) {
      previousRefreshTriggerRef.current = editorRefreshTrigger;

      if (documentContentCache.has(activeDocument.id)) {
        return;
      }

      void reloadContent(false);
    }
  }, [
    activeDocument,
    documentContentCache,
    editorRefreshTrigger,
    reloadContent,
  ]);

  useEffect(() => {
    if (
      transcriptionCompleteTimestamp &&
      activeDocument?.kind === "transcription" &&
      activeDocument.id === previousDocIdRef.current
    ) {
      void reloadContent(true);
    }
  }, [transcriptionCompleteTimestamp, activeDocument, reloadContent]);

  useEffect(() => {
    if (!activeDocument) {
      return;
    }

    ignoreEditorUpdatesRef.current = true;
    hasHydratedDocumentRef.current = false;

    if (activeDocument.id !== previousDocIdRef.current) {
      previousDocIdRef.current = activeDocument.id;
    }
  }, [activeDocument]);

  const flushMountedDirtyDrafts = useCallback(async () => {
    await flushAllDirtyDrafts();
  }, []);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        void flushMountedDirtyDrafts();
        flushDirtyDraftsWithKeepalive();
      }
    };

    const handlePageHide = () => {
      void flushMountedDirtyDrafts();
      flushDirtyDraftsWithKeepalive();
    };

    window.addEventListener("pagehide", handlePageHide);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [flushMountedDirtyDrafts]);

  useEffect(() => {
    return () => {
      if (activeDocumentId && hasHydratedDocumentRef.current) {
        void flushDirtyDrafts([String(activeDocumentId)]);
      }
    };
  }, [activeDocumentId]);

  useEffect(() => {
    const previousSnapshot = previousGenerationSnapshotRef.current;
    const justCompleted =
      previousSnapshot.documentId === generationStatus.documentId &&
      !previousSnapshot.isComplete &&
      generationStatus.isComplete;

    previousGenerationSnapshotRef.current = {
      documentId: generationStatus.documentId,
      isComplete: generationStatus.isComplete,
    };

    if (
      !justCompleted ||
      !activeDocument ||
      generationStatus.documentId !== activeDocument.id
    ) {
      return;
    }

    if (generationSuccessTimerRef.current !== null) {
      window.clearTimeout(generationSuccessTimerRef.current);
      generationSuccessTimerRef.current = null;
    }

    setGenerationSuccessDocumentId(activeDocument.id);
    generationSuccessTimerRef.current = window.setTimeout(() => {
      setGenerationSuccessDocumentId((current) =>
        current === activeDocument.id ? null : current
      );
      generationSuccessTimerRef.current = null;
    }, 2000);
  }, [generationStatus, activeDocument]);

  useEffect(() => {
    return () => {
      if (generationSuccessTimerRef.current !== null) {
        window.clearTimeout(generationSuccessTimerRef.current);
        generationSuccessTimerRef.current = null;
      }
    };
  }, []);

  const activeDerivedState = activeDocument
    ? (derivedByDocumentId[String(activeDocument.id)] ?? null)
    : null;
  const activePatchSet = activePatchSetId ? patchSets[activePatchSetId] : null;
  const patchesForDocument =
    activePatchSet && activeDocument
      ? activePatchSet.patches.filter(
          (p) => p.documentId === String(activeDocument.id),
        )
      : [];

  const patchReviewResolutions = useMemo(
    () =>
      editor && patchesForDocument.length > 0
        ? resolvePatchReviewPatches(editor, patchesForDocument)
        : [],
    [
      documentContent,
      documentContentJson,
      editor,
      editorRefreshTrigger,
      patchesForDocument,
    ],
  );

  const selectedPatchStillVisible = selectedPatchId
    ? patchesForDocument.some((patch) => patch.id === selectedPatchId)
    : false;

  useEffect(() => {
    if (patchesForDocument.length === 0) {
      if (selectedPatchId) {
        setSelectedPatch(null);
      }
      return;
    }

    if (!selectedPatchId || selectedPatchStillVisible) {
      return;
    }

    const firstPending =
      patchesForDocument.find((patch) => patch.status === "pending") ??
      patchesForDocument[0];
    setSelectedPatch(firstPending.id);
  }, [
    patchesForDocument,
    selectedPatchId,
    selectedPatchStillVisible,
    setSelectedPatch,
  ]);

  const editorMode =
    patchesForDocument.length > 0
      ? "patch_review"
      : activeDerivedState?.editorMode === "streaming_preview" &&
          activeDerivedState.inProgress
        ? "streaming_preview"
        : activeDocument?.kind === "transcription"
          ? "read_only"
          : "edit";

  const derivedContent =
    editorMode === "streaming_preview"
      ? activeDerivedState?.streamingContent
      : undefined;
  const transcriptionBlocks = activeDerivedState?.transcriptionBlocks ?? [];
  const showSegmentedTranscription =
    activeDocument?.kind === "transcription" && transcriptionBlocks.length > 0;

  useEffect(() => {
    if (!editor) {
      return;
    }

    setPatchReviewDecorations(
      editor,
      editorMode === "patch_review" ? patchReviewResolutions : [],
      selectedPatchId,
    );
  }, [editor, editorMode, patchReviewResolutions, selectedPatchId]);

  useEffect(() => {
    if (!editor) {
      return;
    }

    editor.setEditable(editorMode === "edit");
  }, [editor, editorMode]);

  useEffect(() => {
    if (!editor || !activeDocument) {
      return;
    }

    const hasExternalContent =
      derivedContent !== undefined || contentLoadedSuccessfully;
    if (!hasExternalContent) {
      return;
    }

    const nextMarkdown = derivedContent ?? documentContent ?? "";
    const candidateJson =
      derivedContent == null && isTiptapJsonContent(documentContentJson)
        ? documentContentJson
        : null;
    const nextJson =
      candidateJson &&
      !shouldPreferMarkdownOverJson(nextMarkdown, candidateJson)
        ? candidateJson
        : null;

    const current = readEditorSnapshot(editor);
    const markdownMatches = current.markdown === nextMarkdown;
    const jsonMatches =
      JSON.stringify(current.json ?? null) === JSON.stringify(nextJson ?? null);

    if ((nextJson && jsonMatches) || (!nextJson && markdownMatches)) {
      if (!hasHydratedDocumentRef.current) {
        hasHydratedDocumentRef.current = true;
        window.setTimeout(() => {
          ignoreEditorUpdatesRef.current = false;
        }, 0);
      }
      return;
    }

    ignoreEditorUpdatesRef.current = true;
    editor.commands.setContent(nextJson ?? nextMarkdown, {
      contentType: nextJson ? "json" : "markdown",
      emitUpdate: false,
    });
    hasHydratedDocumentRef.current = true;
    window.setTimeout(() => {
      ignoreEditorUpdatesRef.current = false;
    }, 0);
  }, [
    activeDocument,
    contentLoadedSuccessfully,
    derivedContent,
    documentContent,
    documentContentJson,
    editor,
    editorRefreshTrigger,
  ]);

  useEffect(() => {
    if (!editor || !activeDocument) {
      return;
    }

    const handleUpdate = ({ editor: updatedEditor }: { editor: Editor }) => {
      if (
        ignoreEditorUpdatesRef.current ||
        !hasHydratedDocumentRef.current ||
        !contentLoadedSuccessfully ||
        editorMode !== "edit"
      ) {
        return;
      }

      const snapshot = readEditorSnapshot(updatedEditor);
      handleDraftChange(activeDocument.id, snapshot.markdown, snapshot.json);
      scheduleEditorSave();
    };

    editor.on("update", handleUpdate);

    return () => {
      editor.off("update", handleUpdate);
    };
  }, [activeDocument, editor, editorMode, handleDraftChange, scheduleEditorSave]);

  useEffect(() => {
    if (!editor || !activeDocumentId || editorMode !== "edit") {
      return;
    }

    const unregisterForceSave = registerForceSave(
        String(activeDocumentId),
        async () => {
        await triggerEditorSave();
        },
    );

    return unregisterForceSave;
  }, [activeDocumentId, editor, editorMode, triggerEditorSave]);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }

      if (hasHydratedDocumentRef.current) {
        void triggerEditorSave();
      }
    };
  }, [triggerEditorSave]);

  if (!activeDocument) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-xl font-medium">
        Seleccione un documento
      </div>
    );
  }

  const isStreamingActiveDocument = editorMode === "streaming_preview";
  const isPatchPreviewMode = editorMode === "patch_review";
  const normalizedCanonicalContent = normalizeEditorText(documentContent ?? "");
  const isStalledGeneratedDocument = Boolean(
    activeDocument &&
      contentLoadedSuccessfully &&
      !isLoadingContent &&
      activeDocument.kind === "note" &&
      activeDocument.doctor_template_id &&
      !activeDerivedState?.error &&
      !activeDerivedState?.inProgress &&
      !activeDerivedState?.isComplete &&
      (normalizedCanonicalContent === "" ||
        normalizedCanonicalContent === INITIAL_GENERATION_STATUS_CHUNK),
  );
  const showGenerationRetryBanner = Boolean(
    activeDocument &&
      !isGenerating &&
      ((activeDerivedState?.source === "generation" &&
        activeDerivedState?.error &&
        !activeDerivedState?.inProgress) ||
        isStalledGeneratedDocument),
  );
  const unresolvedPatchCount = patchReviewResolutions.filter(
    (resolution) =>
      resolution.status === "missing" || resolution.status === "unsupported",
  ).length;
  const isStreamingTranscription =
    isStreamingActiveDocument && activeDerivedState?.source === "transcription";
  const streamingStatusCopy = isStreamingTranscription
    ? "Transcribiendo audio…"
    : derivedContent && normalizeEditorText(derivedContent).length > 0
      ? "Generando documento…"
      : "Preparando documento…";
  const streamingHintCopy = isStreamingTranscription
    ? "Los primeros fragmentos aparecerán en unos momentos."
    : derivedContent && normalizeEditorText(derivedContent).length > 0
      ? "Estamos redactando el contenido clínico."
      : "Esto puede tardar unos segundos.";

  return (
    <div className="flex flex-col h-full">
      {isLoadingContent && (
        <div className="bg-gray-100 p-2 text-center text-gray-600 text-sm">
          Cargando contenido…
        </div>
      )}

      {isStreamingActiveDocument && !isStreamingTranscription && (
        <div className="border-b border-violet-200 bg-violet-50 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-violet-500" />
              <span className="font-medium text-violet-900">
                {streamingStatusCopy}
              </span>
            </div>
            {streamingHintCopy && (
              <div className="text-sm text-violet-700">
                {streamingHintCopy}
              </div>
            )}
          </div>

          {activeDerivedState?.error && (
            <div className="mt-2 p-2 bg-red-100 text-red-700 rounded text-sm">
              <strong>Error:</strong> {activeDerivedState.error}
            </div>
          )}
        </div>
      )}

      {isStreamingActiveDocument && !isStreamingTranscription && (
        <div className="h-1 w-full bg-purple-200">
          <div
            className="h-1 bg-purple-600 transition-all duration-300"
            style={{
              width: `${Math.min(
                Math.max((((derivedContent ?? "").length || 0) / 500) * 100, 10),
                95,
              )}%`,
            }}
          />
        </div>
      )}

      {showGenerationRetryBanner && activeDocument && (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="font-medium text-rose-900">
                {isStalledGeneratedDocument
                  ? "La generación anterior no se completó"
                  : "No se pudo generar el documento"}
              </p>
              <p className="text-sm text-rose-700">
                {activeDerivedState?.error ??
                  "Puedes reintentar sobre este mismo documento cuando el servicio esté disponible."}
              </p>
            </div>
            <button
              type="button"
              className="shrink-0 rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-rose-700"
              onClick={() => {
                void retryGeneration(activeDocument.id);
              }}
            >
              Reintentar generación
            </button>
          </div>
        </div>
      )}

      {isPatchPreviewMode && (
        <div className="bg-amber-50 p-2 border-b border-amber-200 text-amber-800 text-sm text-center">
          Revisión de cambios activa. El texto removido aparece tachado y la propuesta en verde junto al cambio.
        </div>
      )}

      {isPatchPreviewMode && patchReviewResolutions.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto border-b border-amber-100 bg-white px-3 py-2 text-xs">
          <span className="shrink-0 font-medium text-slate-600">
            Cambios sugeridos:
          </span>
          {patchReviewResolutions.map((resolution, index) => {
            const isSelected = resolution.patch.id === selectedPatchId;
            const isUnresolved =
              resolution.status === "missing" ||
              resolution.status === "unsupported";
            return (
              <button
                key={resolution.patch.id}
                type="button"
                className={`shrink-0 rounded border px-2 py-1 text-left ${
                  isSelected
                    ? "border-amber-500 bg-amber-100 text-amber-900"
                    : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100"
                }`}
                onClick={() => setSelectedPatch(resolution.patch.id)}
              >
                #{index + 1}{" "}
                <span className={isUnresolved ? "text-red-600" : ""}>
                  {isUnresolved ? "no localizado" : resolution.patch.type}
                </span>
              </button>
            );
          })}
          {unresolvedPatchCount > 0 && (
            <span className="shrink-0 text-[11px] text-amber-700">
              {unresolvedPatchCount} requieren revision desde el panel.
            </span>
          )}
        </div>
      )}

      {generationSuccessDocumentId === activeDocument.id && (
        <div className="bg-green-100 p-2 border-b border-green-200 text-green-800">
          <div className="flex items-center">
            <svg
              className="h-4 w-4 mr-2"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            <span className="font-medium">
              Documento generado
            </span>
          </div>
        </div>
      )}

      {fetchError && (
        <div className="bg-red-100 p-2 text-center text-red-600 text-sm">
          {fetchError}
        </div>
      )}

      <div
        className="border rounded-md flex-1 bg-white overflow-hidden relative"
        onCopy={handleCopy}
      >
        {isCopilotRunning && editorMode === "edit" && (
          <div className="absolute top-0 right-0 pointer-events-none z-10">
            <span className="m-2 px-2 py-0.5 bg-white/80 text-xs text-gray-400 rounded shadow-sm select-none flex items-center gap-1">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
              IA trabajando…
            </span>
          </div>
        )}

        <div className="h-full">
          {showSegmentedTranscription ? (
            <SegmentedTranscriptionView blocks={transcriptionBlocks} />
          ) : (
            <>
              <EditorContent editor={editor} className="medical-document-editor h-full" />
              <SelectionBubbleMenu editor={editor} onCopy={handleCopy} />
              {!documentContent.trim() &&
                !derivedContent &&
                editorMode === "edit" && (
                  <div className="text-gray-400 absolute top-3 left-4 pointer-events-none">
                    Start typing...
                  </div>
                )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default TextArea;
