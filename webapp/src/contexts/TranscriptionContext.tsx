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
import { useVoiceRecorder } from "../features/encuentroHeader/hooks/audio/useVoiceRecorder";
import { useContentContext } from "./ContentContext";
import { useEncuentroContext } from "./EncuentroContext";
import { logger } from "@/lib/logger";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";

const API_URL = import.meta.env.VITE_API_URL;

const getTranscriptionErrorMessage = (error?: string | null) => {
  if (error === "Audio file has expired") {
    return "El audio expiró. Grabe uno nuevo o elimine el audio vencido.";
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
    id_encuentro: number
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

  const [transcriptionDocId, setTranscriptionDocId] = useState<number | null>(
    initialTranscriptionDocId
  );
  const [transcriptionCompleteTimestamp, setTranscriptionCompleteTimestamp] =
    useState<number | null>(null);
  const [hasBeenTranscribed, setHasBeenTranscribed] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const previousEncounterIdRef = useRef<number | null>(null);
  const activeTranscriptionDocumentId = useDocumentDerivedStore(
    (state) => state.activeTranscriptionDocumentId
  );
  const derivedByDocumentId = useDocumentDerivedStore(
    (state) => state.derivedByDocumentId
  );
  const startTranscriptionStream = useDocumentDerivedStore(
    (state) => state.startTranscription
  );
  const updateTranscriptionContent = useDocumentDerivedStore(
    (state) => state.updateTranscriptionContent
  );
  const completeTranscription = useDocumentDerivedStore(
    (state) => state.completeTranscription
  );
  const failTranscription = useDocumentDerivedStore(
    (state) => state.failTranscription
  );
  const clearDocumentDerivedState = useDocumentDerivedStore(
    (state) => state.clearDocumentDerivedState
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
  const effectiveErrorMessage = transcriptionDerivedState?.error ?? errorMessage;

  // Transcription owns the streaming lifecycle for encounter detail so feature
  // components only consume shared state instead of creating parallel SSE flows.
  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const voiceRecorder = useVoiceRecorder(
    encounterId,
    transcriptionDocId ?? undefined
  );

  const loggedSetHasBeenTranscribed = useCallback(
    (value: boolean) => {
      logger.debug(
        "[TRANSCRIPTION][SET] Setting hasBeenTranscribed from %s to %s",
        hasBeenTranscribed,
        value
      );
      setHasBeenTranscribed(value);
    },
    [hasBeenTranscribed]
  );

  const handleTranscriptionComplete = useCallback(() => {
    const complete = async () => {
      setTranscriptionCompleteTimestamp(Date.now());
      setHasBeenTranscribed(true);

      updateEncuentro({ has_been_transcribed: true }).catch((error) =>
        logger.error(
          "[TRANSCRIPTION] Error updating has_been_transcribed:",
          error
        )
      );

      if (!transcriptionDocId) {
        return;
      }

      if (window.documentContentCache) {
        window.documentContentCache.delete(transcriptionDocId);
      }

      try {
        const refreshedContent = await contentContext.fetchDocumentContent(
          transcriptionDocId,
          true
        );
        completeTranscription(
          String(transcriptionDocId),
          refreshedContent ?? undefined
        );
        contentContext.triggerEditorRefresh();
      } catch (error) {
        logger.error("[TRANSCRIPTION] Error fetching updated content:", error);
        completeTranscription(String(transcriptionDocId));
      }
    };

    void complete();
  }, [completeTranscription, contentContext, transcriptionDocId, updateEncuentro]);

  const resetTranscriptionState = useCallback(() => {
    setErrorMessage(null);
    if (transcriptionDocId) {
      clearDocumentDerivedState(String(transcriptionDocId));
    } else if (activeTranscriptionDocumentId) {
      clearDocumentDerivedState(activeTranscriptionDocumentId);
    }
  }, [activeTranscriptionDocumentId, clearDocumentDerivedState, transcriptionDocId]);

  useEffect(() => {
    return () => {
      closeEventSource();
    };
  }, [closeEventSource]);

  useEffect(() => {
    if (encuentro && encuentro.has_been_transcribed !== undefined) {
      const nextValue = !!encuentro.has_been_transcribed;
      if (nextValue !== hasBeenTranscribed) {
        logger.debug(
          "[TRANSCRIPTION][ENCUENTRO] Syncing hasBeenTranscribed from %s to %s",
          hasBeenTranscribed,
          nextValue
        );
        setHasBeenTranscribed(nextValue);
      }
    }
  }, [encuentro, hasBeenTranscribed]);

  useEffect(() => {
    if (
      voiceRecorder.hasBeenTranscribed &&
      !hasBeenTranscribed &&
      !voiceRecorder.isCheckingAudio
    ) {
      logger.debug(
        "[TRANSCRIPTION][RECORDER] Promoting recorder transcription state into shared context"
      );
      setHasBeenTranscribed(true);
    }
  }, [
    voiceRecorder.hasBeenTranscribed,
    hasBeenTranscribed,
    voiceRecorder.isCheckingAudio,
  ]);

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
      encounterId
    );

    closeEventSource();
    resetTranscriptionState();
    setTranscriptionCompleteTimestamp(null);
    setHasBeenTranscribed(false);
    setTranscriptionDocId(initialTranscriptionDocId);
  }, [
    closeEventSource,
    encounterId,
    initialTranscriptionDocId,
    resetTranscriptionState,
    transcriptionDocId,
  ]);

  const getSSEToken = useCallback(
    async (documentId: number): Promise<string | null> => {
      logger.debug(
        "[TRANSCRIPTION] Requesting SSE token for document %s",
        documentId
      );

      try {
        const response = await axiosInstance.post(
          `/api/v1/documents/${documentId}/sse-token`
        );

        if (response.data.success && response.data.token) {
          return response.data.token;
        }

        logger.error(
          "[TRANSCRIPTION] Failed to get SSE token: %s",
          response.data.error
        );
        return null;
      } catch (error) {
        logger.error("[TRANSCRIPTION] Error getting SSE token:", error);
        return null;
      }
    },
    []
  );

  const subscribeToTranscriptionUpdates = useCallback(
    async (documentId: number): Promise<boolean> => {
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

        const apiBaseUrl = API_URL.endsWith("/") ? API_URL.slice(0, -1) : API_URL;
        const sseUrl = `${apiBaseUrl}/api/v1/sse/documents/${documentId}/${token}`;
        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;
        startTranscriptionStream(String(documentId));

        eventSource.onopen = () => {
          logger.debug(
            "[TRANSCRIPTION] SSE connection established for document %s",
            documentId
          );
        };

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.event === "transcription_complete") {
              handleTranscriptionComplete();
              closeEventSource();
              return;
            }

            if (data.event === "transcription_update" && data.content) {
              updateTranscriptionContent(String(documentId), data.content);
            }
          } catch (error) {
            logger.error("[TRANSCRIPTION] Error parsing SSE message:", error);
          }
        };

        eventSource.onerror = (error) => {
          logger.error("[TRANSCRIPTION] SSE connection error:", error);
          const message = "Error en la conexión de actualizaciones en tiempo real";
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
      failTranscription,
      getSSEToken,
      handleTranscriptionComplete,
      startTranscriptionStream,
      updateTranscriptionContent,
    ]
  );

  const transcribeAudio = useCallback(
    async (id_documento_transcripcion: number, id_encuentro: number) => {
      if (!id_documento_transcripcion || !id_encuentro) {
        setErrorMessage(
          "Falta el ID del documento de transcripción o del encuentro"
        );
        return;
      }

      setErrorMessage(null);
      setTranscriptionDocId(id_documento_transcripcion);

      try {
        const subscribed = await subscribeToTranscriptionUpdates(
          id_documento_transcripcion
        );
        if (!subscribed) {
          throw new Error(
            "No se pudieron preparar las actualizaciones en tiempo real"
          );
        }

        if (voiceRecorder.recordingSessionId) {
          return {
            success: true,
            message: "Transcripción por secciones en proceso",
          };
        }

        const response = await axiosInstance.post(
          `/api/v1/transcription/start`,
          {
            document_id: id_documento_transcripcion,
            encounter_id: id_encuentro,
          },
          { timeout: 60000 }
        );

        logger.debug("Transcription initiated:", response.data);
        if (response.data?.success === false) {
          const message = getTranscriptionErrorMessage(
            response.data?.error || response.data?.message
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
            apiError.message
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
      subscribeToTranscriptionUpdates,
      voiceRecorder.recordingSessionId,
    ]
  );

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
        true
      );
      return !!content && content.trim().length > 0;
    } catch (error) {
      logger.error("[TRANSCRIPTION] Error fetching via ContentContext:", error);
    }

    try {
      const response = await axiosInstance.get(
        `/api/v1/documents/${transcriptionDocId}`
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
      void subscribeToTranscriptionUpdates(transcriptionDocId);
    }
    voiceRecorder.startRecording();
  }, [subscribeToTranscriptionUpdates, transcriptionDocId, voiceRecorder]);

  const stopRecording = useCallback(() => {
    voiceRecorder.stopRecording();
    updateEncuentro({ has_been_transcribed: false }).catch((error) =>
      logger.error(
        "[TRANSCRIPTION] Error updating has_been_transcribed:",
        error
      )
    );
    setHasBeenTranscribed(false);
    if (transcriptionDocId) {
      clearDocumentDerivedState(String(transcriptionDocId));
    }
  }, [clearDocumentDerivedState, transcriptionDocId, updateEncuentro, voiceRecorder]);

  const deleteRecording = useCallback(async () => {
    await voiceRecorder.deleteRecording();
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
    recordingSessionId: voiceRecorder.recordingSessionId,
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
      "useTranscriptionContext must be used within a TranscriptionProvider"
    );
  }
  return context;
}

declare global {
  interface Window {
    documentContentCache?: Map<number, string>;
  }
}
