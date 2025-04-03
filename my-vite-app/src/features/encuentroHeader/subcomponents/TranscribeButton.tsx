import React from "react";
import Tooltip from "@/commons/components/Tooltip";
import useTranscription from "../hooks/useTranscription";

interface TranscribeButtonProps {
  transcriptionDocId?: number;
  audioBlob: Blob | null;
  isRecording: boolean;
  audioExists?: boolean;
  onTranscriptionComplete?: () => void; // Add this prop
}

/**
 * Button to trigger audio transcription
 *
 * Uses a custom hook to make API call to transcribe audio
 */
const TranscribeButton: React.FC<TranscribeButtonProps> = ({
  transcriptionDocId,
  audioBlob,
  isRecording,
  audioExists = false,
  onTranscriptionComplete,
}) => {
  const { transcribeAudio, isLoading, transcriptionStatus, errorMessage } =
    useTranscription(onTranscriptionComplete);

  // Determine if we have audio to transcribe
  const hasAudioToTranscribe = audioBlob || audioExists;
  const isDisabled =
    !transcriptionDocId || isRecording || isLoading || !hasAudioToTranscribe;

  const handleTranscribe = async () => {
    console.log("[TRANSCRIBE_BUTTON] Transcribe button clicked");
    if (isDisabled) {
      console.log(
        "[TRANSCRIBE_BUTTON] Button is disabled. Aborting transcription"
      );
      return;
    }

    try {
      // Extract encounter ID from URL path
      const urlParts =
        typeof window !== "undefined"
          ? window.location.pathname.split("/")
          : [];
      const encounterIdFromUrl = parseInt(urlParts[urlParts.length - 1]) || 0;

      if (!encounterIdFromUrl) {
        throw new Error("Could not determine encounter ID");
      }

      if (!transcriptionDocId) {
        throw new Error("Missing transcription document ID");
      }

      console.log(
        `[TRANSCRIBE_BUTTON] Initiating transcription for document ${transcriptionDocId} and encounter ${encounterIdFromUrl}`
      );

      // Call the transcribeAudio function from the hook
      await transcribeAudio(transcriptionDocId, encounterIdFromUrl);
    } catch (error) {
      console.error("[TRANSCRIBE_BUTTON] Error in transcribe handler:", error);
    }
  };

  // Determine button appearance based on state
  const buttonClasses = `
    flex items-center justify-center px-2 py-1 rounded-md
    ${
      isDisabled
        ? "bg-gray-200 text-gray-400 cursor-not-allowed"
        : transcriptionStatus === "success"
        ? "bg-green-500 text-white hover:bg-green-600"
        : transcriptionStatus === "error"
        ? "bg-red-500 text-white hover:bg-red-600"
        : "bg-blue-500 text-white hover:bg-blue-600"
    }
    transition-colors duration-200
  `;

  // Button content based on state
  const renderButtonContent = () => {
    if (isLoading) {
      return (
        <>
          <div className="w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          <span>Transcribiendo...</span>
        </>
      );
    }

    if (transcriptionStatus === "success") {
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
          <span>Transcrito</span>
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
          <span>Error</span>
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
        <span>Transcribir</span>
      </>
    );
  };

  return (
    <div>
      <Tooltip
        content={
          isDisabled
            ? "Debe grabar audio primero"
            : errorMessage || "Transcribir audio a texto"
        }
      >
        <button
          onClick={handleTranscribe}
          disabled={isDisabled}
          className={buttonClasses}
          aria-label="Transcribir audio a texto"
        >
          {renderButtonContent()}
        </button>
      </Tooltip>
    </div>
  );
};

export default TranscribeButton;
