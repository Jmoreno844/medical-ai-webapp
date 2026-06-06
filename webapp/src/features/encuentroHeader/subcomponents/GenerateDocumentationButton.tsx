import React from "react"; // Removed useState, useEffect
import Tooltip from "@/commons/components/Tooltip";
import { useTranscriptionContext } from "@/contexts/TranscriptionContext";
import { useGenerationContext } from "@/contexts/GenerationContext";
import { useAuth } from "@/commons/hooks/useAuth";

/**
 * Button to generate documentation based on transcription
 *
 * Uses TranscriptionContext to check transcription status
 * and GenerationContext to trigger document generation
 *
 * @returns React component
 */
const GenerateDocumentationButton: React.FC = () => {
  // Get state from contexts
  const {
    hasBeenTranscribed,
    // transcriptionDocId, // No longer directly needed here for enabling/disabling
    // checkTranscriptionContent, // Removed complex checking logic
    // freshlyCompleted, // Removed
    // resetFreshlyCompleted, // Removed
    isRecording,
    pendingAudioSections,
    transcriptionStatus,
  } = useTranscriptionContext();

  const { openGenerationModal, isGenerating } = useGenerationContext();
  const { capabilities } = useAuth();
  const canUseClinicalFeatures = capabilities.can_use_clinical_features;

  const isEnabled =
    canUseClinicalFeatures && hasBeenTranscribed && !isRecording && !isGenerating;

  // Dynamic tooltip based on state
  const getTooltipContent = () => {
    // if (isCheckingContent) { // Removed
    //   return "Checking transcription content...";
    // }
    if (isGenerating) {
      return "Generación en curso…";
    }
    if (!canUseClinicalFeatures) {
      return "Tu cuenta no tiene acceso clínico activo";
    }
    if (isRecording) {
      return "Detén la grabación para terminar la transcripción automática";
    }
    if (!hasBeenTranscribed) {
      if (pendingAudioSections > 0 || transcriptionStatus === "pending") {
        return "Espera a que termine la transcripción automática";
      }
      return "Grabe o continúe el audio para producir una transcripción";
    }
    // Optional: Could add a check here using checkTranscriptionContent if needed,
    // but often just relying on hasBeenTranscribed is sufficient for enabling the button.
    // The actual generation process will fail if content is missing.
    return "Generar documentación a partir de la transcripción";
  };

  return (
    <Tooltip content={getTooltipContent()}>
      {/* Use a span wrapper for tooltip when button is disabled */}
      <span className={!isEnabled ? "cursor-not-allowed" : ""}>
        <button
          onClick={openGenerationModal}
          disabled={!isEnabled}
          className={`flex items-center px-3 py-1.5 rounded text-base font-medium transition-colors
                  ${
                    !isEnabled
                      ? "border border-slate-200 bg-slate-50 text-slate-500 cursor-not-allowed"
                      : "bg-purple-500 text-white hover:bg-purple-600 rounded-md"
                  }`}
          aria-label="Generar documentación clínica"
        >
          {/* {isCheckingContent ? ( // Removed
            <div className="w-4 h-4 mr-2 border-2 border-gray-400 border-t-transparent rounded-full animate-spin"></div>
          ) : isGenerating ? ( // Show spinner if generating */}
          {isGenerating ? ( // Show spinner if generating
            <div className="w-4 h-4 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4 mr-1"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true" // Hide decorative icon from screen readers
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          )}
          Generar
        </button>
      </span>
    </Tooltip>
  );
};

export default GenerateDocumentationButton;
