import React, { useState } from "react";
import axiosInstance from "@/utils/axiosInstance";
import Tooltip from "@/components/Tooltip";

interface TranscribeButtonProps {
    transcriptionDocId?: number;
    audioBlob: Blob | null;
    isRecording: boolean;
    audioExists?: boolean; // Add new prop to track if audio exists on server
}

/**
 * Button to trigger audio transcription
 *
 * Makes API call to transcribe recorded audio
 */
const TranscribeButton: React.FC<TranscribeButtonProps> = ({
    transcriptionDocId,
    audioBlob,
    isRecording,
    audioExists = false,
}) => {
    const [isLoading, setIsLoading] = useState(false);
    const [transcriptionStatus, setTranscriptionStatus] = useState<
        "idle" | "success" | "error"
    >("idle");
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    // Update the disabled logic to consider both local audioBlob and remote audioExists
    // The button should be enabled if:
    // 1. We have a transcription doc ID, AND
    // 2. We're not currently recording, AND
    // 3. We're not currently loading, AND
    // 4. Either we have an audio blob locally OR audio exists on the server (but not both)
    const hasAudioToTranscribe = audioBlob || (audioExists && !audioBlob);
    const isDisabled =
        !transcriptionDocId ||
        isRecording ||
        isLoading ||
        !hasAudioToTranscribe;

    const handleTranscribe = async () => {
        if (isDisabled) return;

        setIsLoading(true);
        setTranscriptionStatus("idle");
        setErrorMessage(null);

        try {
            if (audioBlob) {
                // Local audio transcription flow - use existing logic
                // Prepare form data with audio blob
                const formData = new FormData();
                formData.append("audio", audioBlob as Blob, "recording.webm");

                // Make API call to transcribe endpoint
                const response = await axiosInstance.post(
                    `api/transcribir/${transcriptionDocId}`,
                    formData,
                    {
                        headers: {
                            "Content-Type": "multipart/form-data",
                        },
                        timeout: 60000, // 60 seconds timeout for long transcription
                    }
                );

                setTranscriptionStatus("success");
                console.log("Transcription successful:", response.data);
            } else if (audioExists) {
                // Server-side audio transcription flow - just pass the encounter ID
                // Extract encounter ID from URL path
                const urlParts =
                    typeof window !== "undefined"
                        ? window.location.pathname.split("/")
                        : [];
                const encounterIdFromUrl =
                    parseInt(urlParts[urlParts.length - 1]) || 0;

                if (!encounterIdFromUrl) {
                    throw new Error("Could not determine encounter ID");
                }

                // Make API call to transcribe endpoint for existing server audio
                const response = await axiosInstance.post(
                    `api/transcribir_existente/${encounterIdFromUrl}`,
                    { transcription_doc_id: transcriptionDocId },
                    { timeout: 60000 } // 60 seconds timeout for long transcription
                );

                setTranscriptionStatus("success");
                console.log(
                    "Transcription of existing audio successful:",
                    response.data
                );
            }

            // Optional: Show a brief success message then reset
            setTimeout(() => {
                setTranscriptionStatus("idle");
            }, 3000);
        } catch (error: any) {
            console.error("Transcription error:", error);
            setTranscriptionStatus("error");
            setErrorMessage(
                error.response?.data?.message ||
                    error.message ||
                    "Error al transcribir el audio"
            );
        } finally {
            setIsLoading(false);
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
