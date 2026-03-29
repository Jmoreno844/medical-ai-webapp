import { useState, useEffect, useRef } from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";
const API_URL = import.meta.env.VITE_API_URL;

type TranscriptionStatus = "idle" | "pending" | "success" | "error";

export const useTranscription = (onTranscriptionComplete?: () => void) => {
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
  const getSSEToken = async (id_documento: number): Promise<string | null> => {
    logger.debug(
      `[USE_TRANSCRIPTION] Requesting SSE token for document ${id_documento}`
    );
    try {
      const response = await axiosInstance.post(
        `/api/generate-sse-token/${id_documento}`
      );
      if (response.data.success && response.data.token) {
        logger.debug(
          `[USE_TRANSCRIPTION] Received SSE token for document ${id_documento}`
        );
        return response.data.token;
      } else {
        logger.error(
          "[USE_TRANSCRIPTION] Failed to get SSE token:",
          response.data.error
        );
        return null;
      }
    } catch (error) {
      logger.error("[USE_TRANSCRIPTION] Error getting SSE token:", error);
      return null;
    }
  };

  // Function to subscribe to real-time transcription updates
  const subscribeToTranscriptionUpdates = async (
    id_documento: number
  ): Promise<boolean> => {
    logger.debug(
      `[USE_TRANSCRIPTION] Subscribing to transcription updates for document ${id_documento}`
    );
    // First close any existing connections
    if (eventSourceRef.current) {
      logger.debug("[USE_TRANSCRIPTION] Closing existing SSE connection");
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    try {
      // Get secure token for SSE connection
      const token = await getSSEToken(id_documento);
      if (!token) {
        setErrorMessage("Failed to authenticate for real-time updates");
        return false;
      }

      // Create full URL to the SSE endpoint with secure token using API URL from env
      const apiBaseUrl = API_URL.endsWith("/") ? API_URL.slice(0, -1) : API_URL;
      const sseUrl = `${apiBaseUrl}/api/sse/document/${id_documento}/${token}`;
      logger.debug(`[USE_TRANSCRIPTION] Connecting to SSE endpoint: ${sseUrl}`);

      // Create a new EventSource connection
      const eventSource = new EventSource(sseUrl);
      eventSourceRef.current = eventSource;

      // Connection opened
      eventSource.onopen = () => {
        logger.debug(
          `[USE_TRANSCRIPTION] SSE connection established for document ${id_documento}`
        );
      };

      // Message received
      eventSource.onmessage = (event) => {
        logger.debug("[USE_TRANSCRIPTION] SSE message received", event.data);
        try {
          const data = JSON.parse(event.data);
          logger.debug("[USE_TRANSCRIPTION] Parsed SSE data:", data);

          if (data.event === "transcription_complete") {
            logger.debug(
              `[USE_TRANSCRIPTION] Transcription completed for document ${id_documento}`
            );
            setTranscriptionStatus("success");

            // Call the callback when transcription completes
            if (onTranscriptionComplete) {
              logger.debug(
                "[USE_TRANSCRIPTION] Calling onTranscriptionComplete callback"
              );
              onTranscriptionComplete();
            }

            // Close the connection since we no longer need updates
            eventSource.close();
            eventSourceRef.current = null;
          }
        } catch (error) {
          logger.error(
            "[USE_TRANSCRIPTION] Error parsing SSE message:",
            error
          );
        }
      };

      // Error handling
      eventSource.onerror = (error) => {
        logger.error("[USE_TRANSCRIPTION] SSE connection error:", error);
        setErrorMessage("Error in real-time updates connection");

        // Close the connection on error
        eventSource.close();
        eventSourceRef.current = null;
      };

      return true;
    } catch (error) {
      logger.error(
        "[USE_TRANSCRIPTION] Error creating SSE connection:",
        error
      );
      setErrorMessage("Failed to establish real-time updates");
      return false;
    }
  };

  const transcribeAudio = async (
    id_documento_transcripcion: number,
    id_encuentro: number
  ) => {
    if (!id_documento_transcripcion || !id_encuentro) {
      setErrorMessage("Missing transcription document ID or encounter ID");
      setTranscriptionStatus("error");
      return;
    }

    setIsLoading(true);
    setTranscriptionStatus("pending");
    setErrorMessage(null);

    try {
      // Subscribe to real-time updates for this document with secure authentication
      await subscribeToTranscriptionUpdates(id_documento_transcripcion);

      // Make API call to the simplified transcription endpoint
      const response = await axiosInstance.post(
        `/api/transcription/start`,
        {
          document_id: id_documento_transcripcion,
          encounter_id: id_encuentro,
        },
        { timeout: 60000 }
      );

      // Note: We don't immediately set success here anymore
      // The status will be updated via SSE when transcription completes
      logger.debug("Transcription initiated:", response.data);

      return response.data;
    } catch (error: any) {
      logger.error("Transcription error:", error);
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

  // Add a function to reset the transcription state
  const resetTranscriptionState = () => {
    setTranscriptionStatus("idle");
    setErrorMessage(null);
    setIsLoading(false);
  };

  return {
    transcribeAudio,
    isLoading,
    transcriptionStatus,
    errorMessage,
    setTranscriptionStatus,
    resetTranscriptionState, // Add this new function to the returned object
  };
};

export default useTranscription;
