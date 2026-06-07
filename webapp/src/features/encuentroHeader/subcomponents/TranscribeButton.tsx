import React, { useEffect } from "react";
import Tooltip from "@/commons/components/Tooltip";
import { useTranscriptionContext } from "../../../contexts/TranscriptionContext";
import { useParams } from "react-router-dom";

import { logger } from "@/lib/logger";
interface TranscribeButtonProps {
  resetKey?: number; // Used to trigger resets when audio is deleted
}

/**
 * Button to trigger audio transcription
 *
 * Uses TranscriptionContext to handle all state and actions
 */
const TranscribeButton: React.FC<TranscribeButtonProps> = ({
  resetKey = 0,
}) => {
  // Get encounter ID from URL
  const { id } = useParams<{ id: string }>();
  const encounterId = id ? parseInt(id, 10) : 0;

  // Use transcription context
  const {
    transcriptionDocId,
    audioBlob,
    isRecording,
    audioExists,
    isAudioExpired,
    hasBeenTranscribed,
    pendingAudioSections,
    isTranscribing,
    transcriptionStatus,
    errorMessage,
    canRetryTranscription,
    retryTranscription,
    resetTranscriptionState,
    transcribeAudio,
  } = useTranscriptionContext();

  // Reset transcription state when resetKey changes or audio is deleted.
  // Never reset while a retryable error is pending, otherwise mounting this
  // button to offer the retry would immediately clear the error it surfaces.
  useEffect(() => {
    const hasRetryableError =
      transcriptionStatus === "error" && canRetryTranscription;
    if (!audioExists && !audioBlob && !hasRetryableError) {
      resetTranscriptionState();
    }
  }, [
    resetKey,
    audioExists,
    audioBlob,
    transcriptionStatus,
    canRetryTranscription,
    resetTranscriptionState,
  ]);

  const hasRealtimeSession = Boolean(
    pendingAudioSections > 0 || transcriptionStatus === "pending",
  );
  const shouldContinueRealtimeTranscription =
    hasRealtimeSession &&
    !hasBeenTranscribed &&
    transcriptionStatus !== "success";

  // Determine if we have audio to transcribe or a realtime session to follow.
  const hasAudioToTranscribe = Boolean(
    audioBlob || audioExists || hasRealtimeSession,
  );
  const shouldOfferRetry =
    transcriptionStatus === "error" && canRetryTranscription;
  const isDisabled =
    !transcriptionDocId ||
    isRecording ||
    (isTranscribing && !shouldOfferRetry) ||
    (isAudioExpired && !shouldOfferRetry) ||
    (!hasAudioToTranscribe && !shouldOfferRetry);

  const disabledTooltip = isAudioExpired
    ? "El audio expiró. Grabe uno nuevo o elimine el audio vencido."
    : !hasAudioToTranscribe
      ? "Grabe audio primero"
      : isTranscribing
        ? "Transcripción en progreso"
        : shouldContinueRealtimeTranscription
          ? "Continuar seguimiento de la transcripción en curso"
          : "Transcribir audio a texto";

  const handleTranscribe = async () => {
    logger.debug("[TRANSCRIBE_BUTTON] Transcribe button clicked");
    if (isDisabled) {
      logger.debug(
        "[TRANSCRIBE_BUTTON] Button is disabled. Aborting transcription",
      );
      return;
    }

    try {
      if (!transcriptionDocId) {
        throw new Error("Falta el ID del documento de transcripción");
      }

      if (shouldOfferRetry) {
        logger.debug(
          `[TRANSCRIBE_BUTTON] Retrying transcription for document ${transcriptionDocId}`,
        );
        await retryTranscription(transcriptionDocId);
        return;
      }

      logger.debug(
        `[TRANSCRIBE_BUTTON] Initiating transcription for document ${transcriptionDocId} and encounter ${encounterId}`,
      );

      await transcribeAudio(transcriptionDocId, encounterId);
    } catch (error) {
      logger.error("[TRANSCRIBE_BUTTON] Error in transcribe handler:", error);
    }
  };

  // Determine button appearance based on state
  const buttonClasses = `
    flex items-center justify-center px-4 py-2 rounded-md font-medium
    ${
      isDisabled
        ? "bg-gray-200 text-gray-400 cursor-not-allowed"
        : transcriptionStatus === "success"
          ? "bg-teal-500 text-white hover:bg-teal-600"
          : transcriptionStatus === "error"
            ? "bg-red-500 text-white hover:bg-red-600"
            : "bg-purple-500 text-white hover:bg-purple-600"
    }
    transition-colors duration-200
  `;

  const defaultButtonLabel = shouldContinueRealtimeTranscription
    ? "Continuar transcripción"
    : "Transcribir";

  const defaultAriaLabel = shouldContinueRealtimeTranscription
    ? "Continuar transcripción en curso"
    : "Transcribir audio a texto";

  const buttonAriaLabel = shouldOfferRetry
    ? "Reintentar transcripción"
    : defaultAriaLabel;

  // Button content based on state
  const renderButtonContent = () => {
    if (isTranscribing || (isRecording && hasRealtimeSession)) {
      return (
        <>
          <div className="w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          <span>Transcribiendo…</span>
        </>
      );
    }

    if (isAudioExpired) {
      return (
        <>
          <svg
            className="w-4 h-4 mr-1"
            fill="currentColor"
            viewBox="0 0 20 20"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.72-1.36 3.486 0l6.516 11.585c.75 1.334-.213 2.983-1.742 2.983H3.483c-1.529 0-2.492-1.649-1.742-2.983L8.257 3.099zM11 14a1 1 0 10-2 0 1 1 0 002 0zm-1-2a1 1 0 01-1-1V8a1 1 0 112 0v3a1 1 0 01-1 1z"
              clipRule="evenodd"
            ></path>
          </svg>
          <span>Audio expirado</span>
        </>
      );
    }

    if (transcriptionStatus === "success" || hasBeenTranscribed) {
      return (
        <>
          <svg
            className="w-4 h-4 mr-1"
            fill="currentColor"
            viewBox="0 0 20 20"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            ></path>
          </svg>
          <span className="font-medium">Transcrito</span>
        </>
      );
    }

    if (transcriptionStatus === "error") {
      return (
        <>
          <svg
            className="w-4 h-4 mr-1"
            fill="currentColor"
            viewBox="0 0 20 20"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            ></path>
          </svg>
          <span>{shouldOfferRetry ? "Reintentar" : "Error"}</span>
        </>
      );
    }

    return (
      <>
        <svg
          className="w-4 h-4 mr-1"
          fill="currentColor"
          viewBox="0 0 20 20"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            fillRule="evenodd"
            d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z"
            clipRule="evenodd"
          ></path>
        </svg>
        <span className="text-base font-medium">{defaultButtonLabel}</span>
      </>
    );
  };

  return (
    <div>
      <Tooltip
        content={isDisabled ? disabledTooltip : errorMessage || disabledTooltip}
      >
        <button
          onClick={handleTranscribe}
          disabled={isDisabled}
          className={buttonClasses}
          aria-label={buttonAriaLabel}
        >
          {renderButtonContent()}
        </button>
      </Tooltip>
    </div>
  );
};

export default TranscribeButton;
