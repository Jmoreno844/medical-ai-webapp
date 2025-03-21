import { useState, useEffect, useRef } from "react";
import axiosInstance from "@/utils/axiosInstance";
import { env } from "@/lib/env";

type TranscriptionStatus = "idle" | "pending" | "success" | "error";

export const useTranscription = () => {
    const [isLoading, setIsLoading] = useState(false);
    const [transcriptionStatus, setTranscriptionStatus] =
        useState<TranscriptionStatus>("idle");
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    // Store the current EventSource instance
    const eventSourceRef = useRef<EventSource | null>(null);

    // Cleanup function when component unmounts
    useEffect(() => {
        return () => {
            // Close any open SSE connections when component unmounts
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }
        };
    }, []);

    // Function to get a secure SSE token
    const getSSEToken = async (documentId: number): Promise<string | null> => {
        try {
            const response = await axiosInstance.post(
                `/api/generate-sse-token/${documentId}`
            );
            if (response.data.success && response.data.token) {
                return response.data.token;
            } else {
                console.error("Failed to get SSE token:", response.data.error);
                return null;
            }
        } catch (error) {
            console.error("Error getting SSE token:", error);
            return null;
        }
    };

    // Function to subscribe to real-time transcription updates
    const subscribeToTranscriptionUpdates = async (
        documentId: number
    ): Promise<boolean> => {
        // First close any existing connections
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }

        try {
            // Get secure token for SSE connection
            const token = await getSSEToken(documentId);
            if (!token) {
                setErrorMessage("Failed to authenticate for real-time updates");
                return false;
            }

            // Create full URL to the SSE endpoint with secure token using API URL from env
            const apiBaseUrl = env.NEXT_PUBLIC_API_URL.endsWith("/")
                ? env.NEXT_PUBLIC_API_URL.slice(0, -1)
                : env.NEXT_PUBLIC_API_URL;
            const sseUrl = `${apiBaseUrl}/api/sse/documento/${documentId}/${token}`;

            // Create a new EventSource connection
            const eventSource = new EventSource(sseUrl);
            eventSourceRef.current = eventSource;

            // Connection opened
            eventSource.onopen = () => {
                console.log(
                    "SSE connection established for document",
                    documentId
                );
            };

            // Message received
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log("SSE event received:", data);

                    if (data.event === "transcription_complete") {
                        console.log(
                            "Transcription completed for document",
                            documentId
                        );
                        setTranscriptionStatus("success");

                        // Close the connection since we no longer need updates
                        eventSource.close();
                        eventSourceRef.current = null;
                    }
                } catch (error) {
                    console.error("Error parsing SSE message:", error);
                }
            };

            // Error handling
            eventSource.onerror = (error) => {
                console.error("SSE connection error:", error);
                setErrorMessage("Error in real-time updates connection");

                // Close the connection on error
                eventSource.close();
                eventSourceRef.current = null;
            };

            return true;
        } catch (error) {
            console.error("Error creating SSE connection:", error);
            setErrorMessage("Failed to establish real-time updates");
            return false;
        }
    };

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
        setTranscriptionStatus("pending");
        setErrorMessage(null);

        try {
            // Subscribe to real-time updates for this document with secure authentication
            await subscribeToTranscriptionUpdates(transcriptionDocId);

            // Make API call to the simplified transcription endpoint
            const response = await axiosInstance.post(
                `api/iniciar_transcripcion`,
                {
                    documento_id: transcriptionDocId,
                    encuentro_id: encounterId,
                },
                { timeout: 60000 } // 60 seconds timeout for long transcription
            );

            // Note: We don't immediately set success here anymore
            // The status will be updated via SSE when transcription completes
            console.log("Transcription initiated:", response.data);

            return response.data;
        } catch (error: any) {
            console.error("Transcription error:", error);
            setTranscriptionStatus("error");
            setErrorMessage(
                error.response?.data?.message ||
                    error.message ||
                    "Error al transcribir el audio"
            );

            // Close SSE connection on error
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }

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
