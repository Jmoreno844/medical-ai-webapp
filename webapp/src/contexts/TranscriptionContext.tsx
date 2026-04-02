import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { useVoiceRecorder } from "../features/encuentroHeader/hooks/audio/useVoiceRecorder";
import { useContentContext } from "./ContentContext";
import { useEncuentroContext } from "./EncuentroContext";
import { logger } from "@/lib/logger";

const API_URL = import.meta.env.VITE_API_URL;

type TranscriptionContextType = {
  transcriptionDocId: number | null;
  transcriptionCompleteTimestamp: number | null;
  hasBeenTranscribed: boolean;
  isRecording: boolean;
  isPaused: boolean;
  duration: number;
  audioBlob: Blob | null;
  audioExists: boolean;
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
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcriptionStatus, setTranscriptionStatus] = useState<
    "idle" | "pending" | "success" | "error"
  >("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const previousEncounterIdRef = useRef<number | null>(null);

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

    contentContext
      .fetchDocumentContent(transcriptionDocId, true)
      .then(() => {
        contentContext.triggerEditorRefresh();
      })
      .catch((error) => {
        logger.error("[TRANSCRIPTION] Error fetching updated content:", error);
      });
  }, [contentContext, transcriptionDocId, updateEncuentro]);

  const resetTranscriptionState = useCallback(() => {
    setTranscriptionStatus("idle");
    setErrorMessage(null);
    setIsTranscribing(false);
  }, []);

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
          `/api/generate-sse-token/${documentId}`
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
          setErrorMessage(
            "No se pudo autenticar para las actualizaciones en tiempo real"
          );
          return false;
        }

        const apiBaseUrl = API_URL.endsWith("/") ? API_URL.slice(0, -1) : API_URL;
        const sseUrl = `${apiBaseUrl}/api/sse/document/${documentId}/${token}`;
        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;

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
              setTranscriptionStatus("success");
              handleTranscriptionComplete();
              closeEventSource();
              return;
            }

            if (
              data.event === "transcription_update" &&
              data.content &&
              transcriptionDocId
            ) {
              if (window.documentContentCache) {
                window.documentContentCache.set(transcriptionDocId, data.content);
              }

              contentContext.updateDocumentContent(
                transcriptionDocId,
                data.content
              );
              contentContext.triggerEditorRefresh();
            }
          } catch (error) {
            logger.error("[TRANSCRIPTION] Error parsing SSE message:", error);
          }
        };

        eventSource.onerror = (error) => {
          logger.error("[TRANSCRIPTION] SSE connection error:", error);
          setErrorMessage("Error en la conexión de actualizaciones en tiempo real");
          closeEventSource();
        };

        return true;
      } catch (error) {
        logger.error("[TRANSCRIPTION] Error creating SSE connection:", error);
        setErrorMessage("No se pudieron establecer las actualizaciones en tiempo real");
        return false;
      }
    },
    [
      closeEventSource,
      contentContext,
      getSSEToken,
      handleTranscriptionComplete,
      transcriptionDocId,
    ]
  );

  const transcribeAudio = useCallback(
    async (id_documento_transcripcion: number, id_encuentro: number) => {
      if (!id_documento_transcripcion || !id_encuentro) {
        setErrorMessage(
          "Falta el ID del documento de transcripción o del encuentro"
        );
        setTranscriptionStatus("error");
        return;
      }

      setIsTranscribing(true);
      setTranscriptionStatus("pending");
      setErrorMessage(null);
      setTranscriptionDocId(id_documento_transcripcion);

      try {
        await subscribeToTranscriptionUpdates(id_documento_transcripcion);

        const response = await axiosInstance.post(
          `/api/transcription/start`,
          {
            document_id: id_documento_transcripcion,
            encounter_id: id_encuentro,
          },
          { timeout: 60000 }
        );

        logger.debug("Transcription initiated:", response.data);
        return response.data;
      } catch (error: unknown) {
        logger.error("Transcription error:", error);
        setTranscriptionStatus("error");
        const apiError = error as {
          response?: { data?: { message?: string } };
          message?: string;
        };
        setErrorMessage(
          apiError.response?.data?.message ||
            apiError.message ||
            "Error al transcribir el audio"
        );
        closeEventSource();
        throw error;
      } finally {
        setIsTranscribing(false);
      }
    },
    [closeEventSource, subscribeToTranscriptionUpdates]
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
        `/api/documents/${transcriptionDocId}`
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
    voiceRecorder.startRecording();
  }, [voiceRecorder]);

  const stopRecording = useCallback(() => {
    voiceRecorder.stopRecording();
    updateEncuentro({ has_been_transcribed: false }).catch((error) =>
      logger.error(
        "[TRANSCRIPTION] Error updating has_been_transcribed:",
        error
      )
    );
    setHasBeenTranscribed(false);
  }, [updateEncuentro, voiceRecorder]);

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
    isCheckingAudio: voiceRecorder.isCheckingAudio,
    isDeleting: voiceRecorder.isDeleting,
    isTranscribing,
    transcriptionStatus,
    errorMessage,
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
