import { useState } from "react";
import axiosInstance from "@/utils/axiosInstance";

type TranscriptionStatus = "idle" | "success" | "error";

export const useTranscription = () => {
    const [isLoading, setIsLoading] = useState(false);
    const [transcriptionStatus, setTranscriptionStatus] =
        useState<TranscriptionStatus>("idle");
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const transcribeAudio = async (
        transcriptionDocId: number,
        encounterId: number
    ) => {
        if (!transcriptionDocId || !encounterId) {
            setErrorMessage(
                "Missing transcription document ID or encounter ID"
            );
            setTranscriptionStatus("error");
            return;
        }

        setIsLoading(true);
        setTranscriptionStatus("idle");
        setErrorMessage(null);

        try {
            // Make API call to the simplified transcription endpoint
            const response = await axiosInstance.post(
                `api/iniciar_transcripcion`,
                {
                    documento_id: transcriptionDocId,
                    encuentro_id: encounterId,
                },
                { timeout: 60000 } // 60 seconds timeout for long transcription
            );

            setTranscriptionStatus("success");
            console.log("Transcription successful:", response.data);

            // Optional: Show a brief success message then reset
            setTimeout(() => {
                setTranscriptionStatus("idle");
            }, 3000);

            return response.data;
        } catch (error: any) {
            console.error("Transcription error:", error);
            setTranscriptionStatus("error");
            setErrorMessage(
                error.response?.data?.message ||
                    error.message ||
                    "Error al transcribir el audio"
            );
            throw error;
        } finally {
            setIsLoading(false);
        }
    };

    return {
        transcribeAudio,
        isLoading,
        transcriptionStatus,
        errorMessage,
        setTranscriptionStatus,
    };
};

export default useTranscription;
