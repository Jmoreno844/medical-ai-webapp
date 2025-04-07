import React, { useEffect, useState } from "react";
import Tooltip from "@/commons/components/Tooltip";
import { useTranscriptionContext } from "@/contexts/TranscriptionContext";
import { useGenerationContext } from "@/contexts/GenerationContext";

/**
 * Button to generate documentation based on transcription
 *
 * Uses TranscriptionContext to check content availability
 * and GenerationContext to trigger document generation
 *
 * @returns React component
 */
const GenerateDocumentationButton: React.FC = () => {
  // Get state from contexts
  const {
    hasBeenTranscribed,
    transcriptionDocId,
    checkTranscriptionContent,
    freshlyCompleted,
    resetFreshlyCompleted,
    isRecording,
  } = useTranscriptionContext();

  const { openGenerationModal } = useGenerationContext();

  // Local state to track content checking
  const [isCheckingContent, setIsCheckingContent] = useState(false);
  const [hasContent, setHasContent] = useState(false);

  // Dedicated effect for freshly completed transcriptions
  useEffect(() => {
    if (freshlyCompleted && transcriptionDocId) {
      console.log("[GENERATE_BTN] Detected fresh transcription completion");

      // Verify content immediately
      const checkContent = async () => {
        setIsCheckingContent(true);
        try {
          console.log(
            "[GENERATE_BTN] Checking transcription content after completion"
          );
          const contentAvailable = await checkTranscriptionContent();
          console.log(
            `[GENERATE_BTN] Fresh content check result: ${contentAvailable}`
          );
          setHasContent(contentAvailable);
        } catch (error) {
          console.error(
            "[GENERATE_BTN] Error checking content after completion:",
            error
          );
          setHasContent(false);
        } finally {
          setIsCheckingContent(false);
        }
      };

      checkContent();

      // Reset the flag to avoid rechecking
      resetFreshlyCompleted();
    }
  }, [
    freshlyCompleted,
    transcriptionDocId,
    checkTranscriptionContent,
    resetFreshlyCompleted,
  ]);

  // Check content when transcription status changes or on mount
  useEffect(() => {
    // Only proceed if transcription is completed
    if (!hasBeenTranscribed || !transcriptionDocId) {
      setHasContent(false);
      return;
    }

    // Skip checking if we're already handling it in the freshlyCompleted effect
    if (freshlyCompleted) {
      return;
    }
  }, [
    hasBeenTranscribed,
    transcriptionDocId,
    checkTranscriptionContent,
    freshlyCompleted,
  ]);

  // Button is enabled based on three conditions:
  // 1. The transcription has been completed
  // 2. The transcription has content
  // 3. We're not currently recording or checking content
  console.log("hasBeenTranscribed", hasBeenTranscribed);
  console.log("hasContent", hasContent);
  console.log("isRecording", isRecording);
  console.log("isCheckingContent", isCheckingContent);
  const isEnabled = hasBeenTranscribed && !isRecording && !isCheckingContent;

  // Dynamic tooltip based on state
  const getTooltipContent = () => {
    if (isCheckingContent) {
      return "Checking transcription content...";
    }
    if (isRecording) {
      return "Cannot generate while recording";
    }
    if (!hasBeenTranscribed) {
      return "You must transcribe the audio first";
    }

    return "Generate documentation from transcription";
  };

  return (
    <Tooltip content={getTooltipContent()}>
      <button
        onClick={openGenerationModal}
        disabled={!isEnabled}
        className={`flex items-center px-3 py-1.5 rounded text-base font-medium transition-colors
                ${
                  !isEnabled
                    ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                    : "bg-purple-500 text-white hover:bg-purple-700 rounded-md"
                }`}
        title="Generate medical documentation"
      >
        {isCheckingContent ? (
          <div className="w-4 h-4 mr-2 border-2 border-gray-400 border-t-transparent rounded-full animate-spin"></div>
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4 mr-1"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        )}
        Generate
      </button>
    </Tooltip>
  );
};

export default GenerateDocumentationButton;
