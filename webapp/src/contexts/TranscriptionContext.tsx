import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import {
  getRecordingSessionStatus,
  getRecordingSessionStatusForDocument,
  type RecordingSessionStatus,
} from "../features/encuentroHeader/hooks/audio/uploadService";
import { useVoiceRecorder } from "../features/encuentroHeader/hooks/audio/useVoiceRecorder";
import { useContentContext } from "./ContentContext";
import { useEncuentroContext } from "./EncuentroContext";
import { logger } from "@/lib/logger";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
import { buildTranscriptionBlocks } from "@/workspace/utils/transcriptionBlocks";

const API_URL = import.meta.env.VITE_API_URL;

const getTranscriptionErrorMessage = (error?: string | null) => {
  if (error === "Audio file has expired") {
    return "El audio expiró. Grabe uno nuevo o elimine el audio vencido.";
  }

  if (
    error ===
    "Legacy full-audio transcription is no longer supported by FastAPI. Use segmented recording sessions so transcription runs in the worker."
  ) {
    return "Este audio pertenece al flujo anterior y no puede transcribirse. Graba uno nuevo para usar la transcripción por secciones.";
  }

  return error || "Error al transcribir el audio";
};

type TranscriptionContextType = {
  transcriptionDocId: number | null;
  transcriptionCompleteTimestamp: number | null;
  hasBeenTranscribed: boolean;
  isRecording: boolean;
  isPaused: boolean;
  duration: number;
  audioBlob: Blob | null;
  audioExists: boolean;
  recordingSessionId: string | null;
  pendingAudioSections: number;
  audioExpiresAt: string | null;
  isAudioExpired: boolean;
  isCheckingAudio: boolean;
  isDeleting: boolean;
  isTranscribing: boolean;
  transcriptionStatus: "idle" | "pending" | "success" | "error";
  errorMessage: string | null;
  startRecording: () => void;
  stopRecording: () => void;
  pauseResumeRecording: () => void;
  deleteRecording: () => void;
  transcribeAudio: (
    id_documento_transcripcion: number,
    id_encuentro: number,
  ) => Promise<unknown>;
  setHasBeenTranscribed: (value: boolean) => void;
  onTranscriptionComplete: () => void;
  resetTranscriptionState: () => void;
  checkTranscriptionContent: () => Promise<boolean>;
};

const TranscriptionContext = createContext<
  TranscriptionContextType | undefined
>(undefined);

export function TranscriptionProvider({
  children,
  initialTranscriptionDocId = null,
  encounterId,
}: {
  children: React.ReactNode;
  initialTranscriptionDocId?: number | null;
  encounterId: number;
}) {
  const contentContext = useContentContext();
  const { encuentro, updateEncuentro } = useEncuentroContext();
  const activeWorkspaceDocumentId = useWorkspaceStore(
    (state) => state.activeDocumentId,
  );
  const documentsById = useWorkspaceStore((state) => state.documentsById);
  const activeDocumentId = activeWorkspaceDocumentId
    ? Number(activeWorkspaceDocumentId)
    : null;
  const activeDocument = activeWorkspaceDocumentId
    ? documentsById[activeWorkspaceDocumentId] ?? null
    : null;

  const [transcriptionDocId, setTranscriptionDocId] = useState<number | null>(
    initialTranscriptionDocId,
  );
  const [transcriptionCompleteTimestamp, setTranscriptionCompleteTimestamp] =
    useState<number | null>(null);
  const [localHasBeenTranscribed, setLocalHasBeenTranscribed] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [knownRecordingSessionId, setKnownRecordingSessionId] = useState<
    string | null
  >(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const subscribedTranscriptionDocIdRef = useRef<number | null>(null);
  const previousEncounterIdRef = useRef<number | null>(null);
  const activeRecordingSessionIdRef = useRef<string | null>(null);
  const activeTranscriptionDocumentId = useDocumentDerivedStore(
    (state) => state.activeTranscriptionDocumentId,
  );
  const derivedByDocumentId = useDocumentDerivedStore(
    (state) => state.derivedByDocumentId,
  );
  const startTranscriptionStream = useDocumentDerivedStore(
    (state) => state.startTranscription,
  );
  const updateTranscriptionContent = useDocumentDerivedStore(
    (state) => state.updateTranscriptionContent,
  );
  const completeTranscription = useDocumentDerivedStore(
    (state) => state.completeTranscription,
  );
  const failTranscription = useDocumentDerivedStore(
    (state) => state.failTranscription,
  );
  const clearDocumentDerivedState = useDocumentDerivedStore(
    (state) => state.clearDocumentDerivedState,
  );

  const transcriptionDerivedState = useMemo(() => {
    if (transcriptionDocId) {
      return derivedByDocumentId[String(transcriptionDocId)] ?? null;
    }

    if (activeTranscriptionDocumentId) {
      return derivedByDocumentId[activeTranscriptionDocumentId] ?? null;
    }

    return null;
  }, [activeTranscriptionDocumentId, derivedByDocumentId, transcriptionDocId]);

  const transcriptionStatus =
    transcriptionDerivedState?.transcriptionStatus ?? "idle";
  const isTranscribing = Boolean(transcriptionDerivedState?.inProgress);
  const effectiveErrorMessage =
    transcriptionDerivedState?.error ?? errorMessage;
  const hasBeenTranscribed =
    Boolean(encuentro?.has_been_transcribed) ||
    localHasBeenTranscribed ||
    transcriptionStatus === "success";

  // Transcription owns the streaming lifecycle for encounter detail so feature
  // components only consume shared state instead of creating parallel SSE flows.
  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    subscribedTranscriptionDocIdRef.current = null;
  }, []);

  const voiceRecorder = useVoiceRecorder(
    encounterId,
    transcriptionDocId ?? undefined,
  );

  useEffect(() => {
    if (voiceRecorder.recordingSessionId) {
      activeRecordingSessionIdRef.current = voiceRecorder.recordingSessionId;
      setKnownRecordingSessionId(voiceRecorder.recordingSessionId);
    }
  }, [voiceRecorder.recordingSessionId]);

  const applyRecordingSessionState = useCallback(
    (
      documentId: number,
      sessionStatus: RecordingSessionStatus,
      fallbackContent: string,
    ): boolean => {
      const blocks = buildTranscriptionBlocks(sessionStatus.sections);
      const nextContent =
        sessionStatus.consolidated_transcript ?? fallbackContent;
      const hasUsefulBlocks = blocks.length > 0
      const hasCanonicalContent = nextContent.trim().length > 0;

      if (
        !hasUsefulBlocks &&
        !hasCanonicalContent &&
        sessionStatus.status === "recording"
      ) {
        return false;
      }

      activeRecordingSessionIdRef.current = sessionStatus.session_id;
      setKnownRecordingSessionId(sessionStatus.session_id);

      if (sessionStatus.status === "consolidated") {
        completeTranscription(String(documentId), nextContent, blocks);
        return true;
      }

      if (
        sessionStatus.status === "recording" ||
        sessionStatus.status === "finishing" ||
        sessionStatus.status === "consolidating"
      ) {
        updateTranscriptionContent(String(documentId), nextContent, blocks);
        return true;
      }

      if (sessionStatus.status === "needs_review") {
        failTranscription(
          String(documentId),
          getTranscriptionErrorMessage(sessionStatus.error_code),
        );
      }
      return true;
    },
    [completeTranscription, failTranscription, updateTranscriptionContent],
  );

  const loggedSetHasBeenTranscribed = useCallback(
    (value: boolean) => {
      logger.debug(
        "[TRANSCRIPTION][SET] Setting hasBeenTranscribed from %s to %s",
        hasBeenTranscribed,
        value,
      );
      setLocalHasBeenTranscribed(value);
    },
    [hasBeenTranscribed],
  );

  const handleTranscriptionComplete = useCallback(() => {
    const complete = async () => {
      setTranscriptionCompleteTimestamp(Date.now());
      setLocalHasBeenTranscribed(true);

      updateEncuentro({ has_been_transcribed: true }).catch((error) =>
        logger.error(
          "[TRANSCRIPTION] Error updating has_been_transcribed:",
          error,
        ),
      );

      if (!transcriptionDocId) {
        return;
      }

      if (window.documentContentCache) {
        window.documentContentCache.delete(transcriptionDocId);
      }

      try {
        let finalBlocks;
        if (activeRecordingSessionIdRef.current) {
          const sessionStatus = await getRecordingSessionStatus(
            activeRecordingSessionIdRef.current,
          );
          finalBlocks = buildTranscriptionBlocks(sessionStatus?.sections);
        }
        const refreshedContent = await contentContext.fetchDocumentContent(
          transcriptionDocId,
          true,
        );
        completeTranscription(
          String(transcriptionDocId),
          refreshedContent ?? undefined,
          finalBlocks,
        );
        contentContext.triggerEditorRefresh();
      } catch (error) {
        logger.error("[TRANSCRIPTION] Error fetching updated content:", error);
        completeTranscription(String(transcriptionDocId));
      }
    };

    void complete();
  }, [
    completeTranscription,
    contentContext,
    transcriptionDocId,
    updateEncuentro,
  ]);

  const refreshTranscriptionBlocks = useCallback(
    async (
      documentId: number,
      fallbackContent: string,
      mode: "pending" | "complete",
    ): Promise<boolean> => {
      const sessionId = activeRecordingSessionIdRef.current;
      if (!sessionId) {
        return false;
      }

      const sessionStatus = await getRecordingSessionStatus(sessionId);
      if (!sessionStatus) {
        return false;
      }

      const blocks = buildTranscriptionBlocks(sessionStatus.sections);
      const nextContent =
        mode === "complete"
          ? sessionStatus.consolidated_transcript ?? fallbackContent
          : fallbackContent;

      if (mode === "complete") {
        completeTranscription(String(documentId), nextContent, blocks);
      } else {
        updateTranscriptionContent(String(documentId), nextContent, blocks);
      }

      return true;
    },
    [completeTranscription, updateTranscriptionContent],
  );

  const resetTranscriptionState = useCallback(() => {
    setErrorMessage(null);
    activeRecordingSessionIdRef.current = null;
    setKnownRecordingSessionId(null);
    if (transcriptionDocId) {
      clearDocumentDerivedState(String(transcriptionDocId));
    } else if (activeTranscriptionDocumentId) {
      clearDocumentDerivedState(activeTranscriptionDocumentId);
    }
  }, [
    activeTranscriptionDocumentId,
    clearDocumentDerivedState,
    transcriptionDocId,
  ]);

  useEffect(() => {
    return () => {
      closeEventSource();
    };
  }, [closeEventSource]);

  useEffect(() => {
    const previousEncounterId = previousEncounterIdRef.current;
    previousEncounterIdRef.current = encounterId;

    if (previousEncounterId === null) {
      setTranscriptionDocId(initialTranscriptionDocId);
      return;
    }

    if (previousEncounterId === encounterId) {
      if (initialTranscriptionDocId !== transcriptionDocId) {
        setTranscriptionDocId(initialTranscriptionDocId);
      }
      return;
    }

    logger.debug(
      "[TRANSCRIPTION][RESET] Encounter changed to %s; resetting transcription-owned state.",
      encounterId,
    );

    closeEventSource();
    resetTranscriptionState();
    setTranscriptionCompleteTimestamp(null);
    setLocalHasBeenTranscribed(false);
    setTranscriptionDocId(initialTranscriptionDocId);
    activeRecordingSessionIdRef.current = null;
    setKnownRecordingSessionId(null);
  }, [
    closeEventSource,
    encounterId,
    initialTranscriptionDocId,
    resetTranscriptionState,
    transcriptionDocId,
  ]);

  useEffect(() => {
    if (
      !activeDocumentId ||
      String(activeDocument?.metadata?.kind ?? activeDocument?.type) !==
        "transcription"
    ) {
      return;
    }

    let isCancelled = false;

    const hydrateCanonicalSession = async () => {
      const sessionStatus = await getRecordingSessionStatusForDocument(
        activeDocumentId,
      );
      if (!sessionStatus || isCancelled) {
        return;
      }

      const fallbackContent =
        contentContext.documentContentCache.get(activeDocumentId) ??
        (transcriptionDocId === activeDocumentId
          ? contentContext.documentContent
          : "") ??
        "";

      const applied = applyRecordingSessionState(
        activeDocumentId,
        sessionStatus,
        fallbackContent,
      );
      if (!applied && !voiceRecorder.recordingSessionId) {
        activeRecordingSessionIdRef.current = null;
        setKnownRecordingSessionId(null);
      }
    };

    void hydrateCanonicalSession();

    return () => {
      isCancelled = true;
    };
  }, [
    activeDocument?.metadata?.kind,
    activeDocument?.type,
    activeDocumentId,
    applyRecordingSessionState,
    contentContext.documentContent,
    contentContext.documentContentCache,
    transcriptionDocId,
    voiceRecorder.recordingSessionId,
  ]);

  const getSSEToken = useCallback(
    async (documentId: number): Promise<string | null> => {
      logger.debug(
        "[TRANSCRIPTION] Requesting SSE token for document %s",
        documentId,
      );

      try {
        const response = await axiosInstance.post(
          `/api/v1/documents/${documentId}/sse-token`,
        );

        if (response.data.success && response.data.token) {
          return response.data.token;
        }

        logger.error(
          "[TRANSCRIPTION] Failed to get SSE token: %s",
          response.data.error,
        );
        return null;
      } catch (error) {
        logger.error("[TRANSCRIPTION] Error getting SSE token:", error);
        return null;
      }
    },
    [],
  );

  const subscribeToTranscriptionUpdates = useCallback(
    async (
      documentId: number,
      options: { markPendingOnConnect?: boolean } = {},
    ): Promise<boolean> => {
      closeEventSource();

      try {
        const token = await getSSEToken(documentId);
        if (!token) {
          const message =
            "No se pudo autenticar para las actualizaciones en tiempo real";
          setErrorMessage(message);
          failTranscription(String(documentId), message);
          return false;
        }

        const apiBaseUrl = API_URL.endsWith("/")
          ? API_URL.slice(0, -1)
          : API_URL;
        const sseUrl = `${apiBaseUrl}/api/v1/sse/documents/${documentId}/${token}`;
        let initialStreamingContent =
          contentContext.documentContentCache.get(documentId) ??
          (transcriptionDocId === documentId
            ? contentContext.documentContent
            : undefined);
        if (initialStreamingContent === undefined) {
          initialStreamingContent =
            (await contentContext.fetchDocumentContent(documentId)) ?? undefined;
        }
        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;
        subscribedTranscriptionDocIdRef.current = documentId;
        if (options.markPendingOnConnect ?? true) {
          startTranscriptionStream(String(documentId), initialStreamingContent);
        }

        eventSource.onopen = () => {
          logger.debug(
            "[TRANSCRIPTION] SSE connection established for document %s",
            documentId,
          );
        };

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            logger.debug("[TRANSCRIPTION] SSE event received", {
              documentId,
              event: data?.event,
              hasContent: typeof data?.content === "string",
              contentLength:
                typeof data?.content === "string" ? data.content.length : 0,
            });

            if (
              data?.event === "transcription_update" &&
              typeof data?.content === "string"
            ) {
              logger.sensitiveDebug("[TRANSCRIPTION] SSE content", {
                documentId,
                content: data.content,
              });
            }

            if (data.event === "transcription_complete") {
              void refreshTranscriptionBlocks(
                documentId,
                typeof data?.content === "string" ? data.content : "",
                "complete",
              );
              handleTranscriptionComplete();
              closeEventSource();
              return;
            }

            if (data.event === "transcription_update" && data.content) {
              void refreshTranscriptionBlocks(
                documentId,
                String(data.content),
                "pending",
              ).then((refreshed) => {
                if (!refreshed) {
                  updateTranscriptionContent(String(documentId), data.content);
                }
              });
              return;
            }

            if (data.event === "transcription_update") {
              logger.warn(
                "[TRANSCRIPTION] SSE update arrived without usable content",
                {
                  documentId,
                  contentType: typeof data?.content,
                },
              );
            }
          } catch (error) {
            logger.error("[TRANSCRIPTION] Error parsing SSE message:", error);
          }
        };

        eventSource.onerror = (error) => {
          logger.error("[TRANSCRIPTION] SSE connection error:", error);
          const message =
            "Error en la conexión de actualizaciones en tiempo real";
          setErrorMessage(message);
          failTranscription(String(documentId), message);
          closeEventSource();
        };

        return true;
      } catch (error) {
        logger.error("[TRANSCRIPTION] Error creating SSE connection:", error);
        const message =
          "No se pudieron establecer las actualizaciones en tiempo real";
        setErrorMessage(message);
        failTranscription(String(documentId), message);
        return false;
      }
    },
    [
      closeEventSource,
      contentContext,
      failTranscription,
      getSSEToken,
      handleTranscriptionComplete,
      refreshTranscriptionBlocks,
      startTranscriptionStream,
      transcriptionDocId,
      updateTranscriptionContent,
    ],
  );

  const transcribeAudio = useCallback(
    async (id_documento_transcripcion: number, id_encuentro: number) => {
      if (!id_documento_transcripcion || !id_encuentro) {
        setErrorMessage(
          "Falta el ID del documento de transcripción o del encuentro",
        );
        return;
      }

      setErrorMessage(null);
      setTranscriptionDocId(id_documento_transcripcion);

      try {
        const subscribed = await subscribeToTranscriptionUpdates(
          id_documento_transcripcion,
          {
            markPendingOnConnect: false,
          },
        );
        if (!subscribed) {
          throw new Error(
            "No se pudieron preparar las actualizaciones en tiempo real",
          );
        }

        if (
          !hasBeenTranscribed &&
          (voiceRecorder.pendingAudioSections > 0 ||
            transcriptionStatus === "pending")
        ) {
          return {
            success: true,
            message: "Transcripción por secciones en proceso",
          };
        }

        if (
          voiceRecorder.audioExists &&
          voiceRecorder.pendingAudioSections === 0 &&
          !knownRecordingSessionId
        ) {
          const message =
            "Este audio pertenece al flujo anterior y no puede transcribirse. Graba uno nuevo para usar la transcripción por secciones.";
          setErrorMessage(message);
          failTranscription(String(id_documento_transcripcion), message);
          closeEventSource();
          throw new Error(message);
        }

        const response = await axiosInstance.post(
          `/api/v1/transcription/start`,
          {
            document_id: id_documento_transcripcion,
            encounter_id: id_encuentro,
          },
          { timeout: 60000 },
        );

        logger.debug("Transcription initiated:", response.data);
        if (response.data?.success === false) {
          const message = getTranscriptionErrorMessage(
            response.data?.error || response.data?.message,
          );
          setErrorMessage(message);
          failTranscription(String(id_documento_transcripcion), message);
          closeEventSource();
          throw new Error(message);
        }
        return response.data;
      } catch (error: unknown) {
        logger.error("Transcription error:", error);
        const apiError = error as {
          response?: { data?: { error?: string; message?: string } };
          message?: string;
        };
        const message = getTranscriptionErrorMessage(
          apiError.response?.data?.error ||
            apiError.response?.data?.message ||
            apiError.message,
        );
        setErrorMessage(message);
        failTranscription(String(id_documento_transcripcion), message);
        closeEventSource();
        throw error;
      }
    },
    [
      closeEventSource,
      failTranscription,
      hasBeenTranscribed,
      knownRecordingSessionId,
      subscribeToTranscriptionUpdates,
      transcriptionStatus,
      voiceRecorder.audioExists,
      voiceRecorder.pendingAudioSections,
    ],
  );

  useEffect(() => {
    if (!transcriptionDocId || hasBeenTranscribed) {
      return;
    }

    const hasBackgroundTranscriptionWork =
      voiceRecorder.pendingAudioSections > 0 ||
      transcriptionStatus === "pending";

    if (!hasBackgroundTranscriptionWork) {
      return;
    }

    if (
      eventSourceRef.current &&
      subscribedTranscriptionDocIdRef.current === transcriptionDocId
    ) {
      return;
    }

    void subscribeToTranscriptionUpdates(transcriptionDocId);
  }, [
    hasBeenTranscribed,
    knownRecordingSessionId,
    subscribeToTranscriptionUpdates,
    transcriptionDocId,
    transcriptionStatus,
    voiceRecorder.pendingAudioSections,
  ]);

  /**
   * Generation depends on this lookup to avoid using stale empty transcription
   * state, so the fallback stays here with the transcription owner.
   */
  const checkTranscriptionContent = useCallback(async (): Promise<boolean> => {
    if (!transcriptionDocId) {
      return false;
    }

    if (window.documentContentCache?.has(transcriptionDocId)) {
      const content = window.documentContentCache.get(transcriptionDocId);
      return !!content && content.trim().length > 0;
    }

    try {
      const content = await contentContext.fetchDocumentContent(
        transcriptionDocId,
        true,
      );
      return !!content && content.trim().length > 0;
    } catch (error) {
      logger.error("[TRANSCRIPTION] Error fetching via ContentContext:", error);
    }

    try {
      const response = await axiosInstance.get(
        `/api/v1/documents/${transcriptionDocId}`,
      );
      const content = response.data?.content || "";

      if (content) {
        if (window.documentContentCache) {
          window.documentContentCache.set(transcriptionDocId, content);
        }
        contentContext.updateDocumentContent(transcriptionDocId, content);
      }

      return !!content && content.trim().length > 0;
    } catch (error) {
      logger.error("[TRANSCRIPTION] Error in direct API fetch:", error);
      return false;
    }
  }, [contentContext, transcriptionDocId]);

  const startRecording = useCallback(() => {
    if (transcriptionDocId) {
      void subscribeToTranscriptionUpdates(transcriptionDocId, {
        markPendingOnConnect: !hasBeenTranscribed,
      });
    }
    voiceRecorder.startRecording();
  }, [
    hasBeenTranscribed,
    subscribeToTranscriptionUpdates,
    transcriptionDocId,
    voiceRecorder,
  ]);

  const stopRecording = useCallback(() => {
    voiceRecorder.stopRecording();
  }, [voiceRecorder]);

  const deleteRecording = useCallback(async () => {
    await voiceRecorder.deleteRecording();
    activeRecordingSessionIdRef.current = null;
    setKnownRecordingSessionId(null);
  }, [voiceRecorder]);

  const value: TranscriptionContextType = {
    transcriptionDocId,
    transcriptionCompleteTimestamp,
    hasBeenTranscribed,
    isRecording: voiceRecorder.isRecording,
    isPaused: voiceRecorder.isPaused,
    duration: voiceRecorder.duration,
    audioBlob: voiceRecorder.audioBlob,
    audioExists: voiceRecorder.audioExists,
    recordingSessionId: knownRecordingSessionId,
    pendingAudioSections: voiceRecorder.pendingAudioSections,
    audioExpiresAt: voiceRecorder.audioExpiresAt,
    isAudioExpired: voiceRecorder.isAudioExpired,
    isCheckingAudio: voiceRecorder.isCheckingAudio,
    isDeleting: voiceRecorder.isDeleting,
    isTranscribing,
    transcriptionStatus,
    errorMessage: effectiveErrorMessage,
    startRecording,
    stopRecording,
    pauseResumeRecording: voiceRecorder.pauseResumeRecording,
    deleteRecording,
    transcribeAudio,
    setHasBeenTranscribed: loggedSetHasBeenTranscribed,
    onTranscriptionComplete: handleTranscriptionComplete,
    resetTranscriptionState,
    checkTranscriptionContent,
  };

  return (
    <TranscriptionContext.Provider value={value}>
      {children}
    </TranscriptionContext.Provider>
  );
}

export function useTranscriptionContext() {
  const context = useContext(TranscriptionContext);
  if (context === undefined) {
    throw new Error(
      "useTranscriptionContext must be used within a TranscriptionProvider",
    );
  }
  return context;
}

declare global {
  interface Window {
    documentContentCache?: Map<number, string>;
  }
}
