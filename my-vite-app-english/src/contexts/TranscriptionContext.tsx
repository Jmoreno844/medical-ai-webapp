import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { useVoiceRecorder } from "../features/encuentroHeader/hooks/audio/useVoiceRecorder";
import { useContentContext } from "./ContentContext"; // Add ContentContext import
import { useEncuentroContext } from "./EncuentroContext"; // Add EncuentroContext import

const API_URL = import.meta.env.VITE_API_URL;

// Define the context type
type TranscriptionContextType = {
  // Transcription document state
  transcriptionDocId: number | null;
  transcriptionCompleteTimestamp: number | null;
  hasBeenTranscribed: boolean;

  // Recording state
  isRecording: boolean;
  isPaused: boolean;
  duration: number;
  audioBlob: Blob | null;
  audioExists: boolean;
  isCheckingAudio: boolean;
  isDeleting: boolean;

  // Transcription process state
  isTranscribing: boolean;
  transcriptionStatus: "idle" | "pending" | "success" | "error";
  errorMessage: string | null;

  // Audio recording actions
  startRecording: () => void;
  stopRecording: () => void;
  pauseResumeRecording: () => void;
  deleteRecording: () => void;

  // Transcription actions
  transcribeAudio: (
    id_documento_transcripcion: number,
    id_encuentro: number
  ) => Promise<any>;
  setHasBeenTranscribed: (value: boolean) => void;
  onTranscriptionComplete: () => void;
  resetTranscriptionState: () => void;

  // New method to check transcription content
  checkTranscriptionContent: () => Promise<boolean>;
};

// Create the context
const TranscriptionContext = createContext<
  TranscriptionContextType | undefined
>(undefined);

// Create the provider
export function TranscriptionProvider({
  children,
  initialTranscriptionDocId = null,
  encounterId,
}: {
  children: React.ReactNode;
  initialTranscriptionDocId?: number | null;
  encounterId: number;
}) {
  // Get ContentContext access
  const contentContext = useRef<ReturnType<typeof useContentContext> | null>(
    null
  );

  // Get EncuentroContext access
  const { encuentro, updateEncuentro } = useEncuentroContext();

  // Use try-catch to avoid errors if ContentContext is not yet available
  try {
    contentContext.current = useContentContext();
  } catch (error) {
    console.warn("[TRANSCRIPTION] ContentContext not yet available");
  }

  // Track transcription document
  const [transcriptionDocId, setTranscriptionDocId] = useState<number | null>(
    initialTranscriptionDocId
  );
  const [transcriptionCompleteTimestamp, setTranscriptionCompleteTimestamp] =
    useState<number | null>(null);
  const [hasBeenTranscribed, setHasBeenTranscribed] = useState<boolean>(false);

  // Ref to track initial mount
  const isInitialMount = useRef(true);

  // Move the initial log into a useEffect with empty dependency array to run only once on mount
  useEffect(() => {
    console.log(
      `[TRANSCRIPTION][INIT] hasBeenTranscribed initial value: ${hasBeenTranscribed}`
    );
  }, []);

  // Wrap setState to add logging
  const loggedSetHasBeenTranscribed = (value: boolean) => {
    console.log(
      `[TRANSCRIPTION][SET] Setting hasBeenTranscribed from ${hasBeenTranscribed} to ${value}, source: explicit call`
    );
    setHasBeenTranscribed(value);
  };

  // Add direct state management instead of using useTranscription hook
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcriptionStatus, setTranscriptionStatus] = useState<
    "idle" | "pending" | "success" | "error"
  >("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Create a ref for encounterID to use in callbacks
  const encounterIdRef = useRef<number>(encounterId);

  // Update encounter ID ref when prop changes
  useEffect(() => {
    encounterIdRef.current = encounterId;
  }, [encounterId]);

  // Store the current EventSource instance
  const eventSourceRef = useRef<EventSource | null>(null);

  // Enhanced handleTranscriptionComplete function
  const handleTranscriptionComplete = useCallback(() => {
    setTranscriptionCompleteTimestamp(Date.now());
    console.log(
      `[TRANSCRIPTION][COMPLETE] Setting hasBeenTranscribed from ${hasBeenTranscribed} to true, source: transcriptionComplete`
    );
    setHasBeenTranscribed(true);

    // Update the encuentro context and backend
    updateEncuentro({ has_been_transcribed: true }).catch((error) =>
      console.error(
        "[TRANSCRIPTION] Error updating has_been_transcribed:",
        error
      )
    );

    // If transcription document exists
    if (transcriptionDocId) {
      console.log(
        `[TRANSCRIPTION] Transcription completed for document ${transcriptionDocId}`
      );

      // Clear the cache so we can get fresh content
      if (window.documentContentCache) {
        console.log(
          `[TRANSCRIPTION] Clearing cache for document ${transcriptionDocId}`
        );
        window.documentContentCache.delete(transcriptionDocId);
      }

      // Force fetch fresh content from the server if ContentContext is available
      if (contentContext.current) {
        contentContext.current
          .fetchDocumentContent(transcriptionDocId, true)
          .then((content) => {
            console.log(
              `[TRANSCRIPTION] Fetched fresh content for document ${transcriptionDocId}`
            );

            // Trigger editor refresh to ensure content is updated in the editor
            contentContext.current?.triggerEditorRefresh();
          })
          .catch((error) => {
            console.error(
              `[TRANSCRIPTION] Error fetching updated content:`,
              error
            );
          });
      }
    }
  }, [transcriptionDocId, updateEncuentro, hasBeenTranscribed]);

  // Use the voice recorder hook with transcription document ID
  const voiceRecorder = useVoiceRecorder(transcriptionDocId);

  // Add a function to reset the transcription state
  const resetTranscriptionState = () => {
    setTranscriptionStatus("idle");
    setErrorMessage(null);
    setIsTranscribing(false);
  };

  // Monitor the hasBeenTranscribed value from the recorder and sync it
  useEffect(() => {
    console.log(
      `[TRANSCRIPTION][SYNC] Recorder hasBeenTranscribed: ${voiceRecorder.hasBeenTranscribed}, context hasBeenTranscribed: ${hasBeenTranscribed}`
    );

    // Only pull in the recorder's "true" value.
    // If SSE/Context is already true, keep it that way.
    if (
      voiceRecorder.hasBeenTranscribed === true &&
      hasBeenTranscribed === false
    ) {
      console.log(
        `[TRANSCRIPTION][SYNC] Setting hasBeenTranscribed from ${hasBeenTranscribed} to true, source: recorder sync`
      );
      setHasBeenTranscribed(true);
    }
  }, [voiceRecorder.hasBeenTranscribed, hasBeenTranscribed]);

  // Set transcription ID when it's discovered
  useEffect(() => {
    if (
      initialTranscriptionDocId &&
      initialTranscriptionDocId !== transcriptionDocId
    ) {
      setTranscriptionDocId(initialTranscriptionDocId);
    }
  }, [initialTranscriptionDocId, transcriptionDocId]);

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
    console.log(
      `[USE_TRANSCRIPTION] Requesting SSE token for document ${id_documento}`
    );
    try {
      const response = await axiosInstance.post(
        `/api/generate-sse-token/${id_documento}`
      );
      if (response.data.success && response.data.token) {
        console.log(
          `[USE_TRANSCRIPTION] Received SSE token for document ${id_documento}`
        );
        return response.data.token;
      } else {
        console.error(
          "[USE_TRANSCRIPTION] Failed to get SSE token:",
          response.data.error
        );
        return null;
      }
    } catch (error) {
      console.error("[USE_TRANSCRIPTION] Error getting SSE token:", error);
      return null;
    }
  };

  // Function to subscribe to real-time transcription updates
  const subscribeToTranscriptionUpdates = async (
    id_documento: number
  ): Promise<boolean> => {
    console.log(
      `[USE_TRANSCRIPTION] Subscribing to transcription updates for document ${id_documento}`
    );
    // First close any existing connections
    if (eventSourceRef.current) {
      console.log("[USE_TRANSCRIPTION] Closing existing SSE connection");
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
      const sseUrl = `${apiBaseUrl}/api/sse/documento/${id_documento}/${token}`;
      console.log(`[USE_TRANSCRIPTION] Connecting to SSE endpoint: ${sseUrl}`);

      // Create a new EventSource connection
      const eventSource = new EventSource(sseUrl);
      eventSourceRef.current = eventSource;

      // Connection opened
      eventSource.onopen = () => {
        console.log(
          `[USE_TRANSCRIPTION] SSE connection established for document ${id_documento}`
        );
      };

      // Message received - enhanced with content updates
      eventSource.onmessage = (event) => {
        console.log("[USE_TRANSCRIPTION] SSE message received", event.data);
        try {
          const data = JSON.parse(event.data);
          console.log("[USE_TRANSCRIPTION] Parsed SSE data:", data);

          if (data.event === "transcription_complete") {
            console.log(
              `[USE_TRANSCRIPTION] Transcription completed for document ${id_documento}`
            );
            setTranscriptionStatus("success");

            console.log(
              `[TRANSCRIPTION][SSE] Setting hasBeenTranscribed from ${hasBeenTranscribed} to true, source: SSE transcription_complete`
            );
            setHasBeenTranscribed(true);

            // Call the callback when transcription completes
            console.log(
              "[USE_TRANSCRIPTION] Calling onTranscriptionComplete callback"
            );
            handleTranscriptionComplete();

            // Close the connection since we no longer need updates
            eventSource.close();
            eventSourceRef.current = null;
          }

          // If we receive content updates during transcription
          if (data.event === "transcription_update" && data.content) {
            console.log(
              `[USE_TRANSCRIPTION] Received content update for document ${id_documento}`
            );

            // Update cache with intermediate content if available
            if (window.documentContentCache && transcriptionDocId) {
              window.documentContentCache.set(transcriptionDocId, data.content);

              // If ContentContext is available, update content and trigger refresh
              if (contentContext.current) {
                contentContext.current.updateDocumentContent(
                  transcriptionDocId,
                  data.content
                );
                contentContext.current.triggerEditorRefresh();
              }
            }
          }
        } catch (error) {
          console.error(
            "[USE_TRANSCRIPTION] Error parsing SSE message:",
            error
          );
        }
      };

      // Error handling
      eventSource.onerror = (error) => {
        console.error("[USE_TRANSCRIPTION] SSE connection error:", error);
        setErrorMessage("Error in real-time updates connection");

        // Close the connection on error
        eventSource.close();
        eventSourceRef.current = null;
      };

      return true;
    } catch (error) {
      console.error(
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

    setIsTranscribing(true);
    setTranscriptionStatus("pending");
    setErrorMessage(null);
    setTranscriptionDocId(id_documento_transcripcion);

    try {
      // Subscribe to real-time updates for this document with secure authentication
      await subscribeToTranscriptionUpdates(id_documento_transcripcion);

      // Make API call to the simplified transcription endpoint
      const response = await axiosInstance.post(
        `api/iniciar_transcripcion`,
        {
          id_documento: id_documento_transcripcion,
          id_encuentro: id_encuentro,
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
      setIsTranscribing(false);
    }
  };

  /**
   * Checks if the transcription document has content
   * Uses ContentContext if available, otherwise makes a direct API call
   * Also ensures content is properly cached
   *
   * @returns Promise resolving to true if content exists and is not empty
   */
  const checkTranscriptionContent = useCallback(async (): Promise<boolean> => {
    if (!transcriptionDocId) return false;

    console.log(
      `[TRANSCRIPTION] Checking content for document ${transcriptionDocId}`
    );

    // First check if content is in cache
    if (window.documentContentCache?.has(transcriptionDocId)) {
      const content = window.documentContentCache.get(transcriptionDocId);
      const hasContent = !!content && content.trim().length > 0;
      console.log(
        `[TRANSCRIPTION] Content found in cache: ${
          hasContent ? "Not empty" : "Empty"
        }`
      );
      return hasContent;
    }

    console.log(`[TRANSCRIPTION] Content not in cache, fetching from server`);

    // If ContentContext is available, try using it
    if (contentContext.current) {
      try {
        console.log(`[TRANSCRIPTION] Using ContentContext to fetch content`);
        const content = await contentContext.current.fetchDocumentContent(
          transcriptionDocId,
          true
        );
        const hasContent = !!content && content.trim().length > 0;
        console.log(
          `[TRANSCRIPTION] Content fetched via context: ${
            hasContent ? "Not empty" : "Empty"
          }`
        );
        return hasContent;
      } catch (error) {
        console.error(
          `[TRANSCRIPTION] Error fetching via ContentContext:`,
          error
        );
      }
    }

    // Fallback to direct API call
    try {
      console.log(`[TRANSCRIPTION] Fallback: Direct API call`);
      const response = await axiosInstance.get(
        `/api/documento/${transcriptionDocId}`
      );
      const content = response.data?.contenido || "";

      // Save to cache
      if (content) {
        console.log(`[TRANSCRIPTION] Saving fetched content to cache`);

        // Update window cache for compatibility
        if (window.documentContentCache) {
          window.documentContentCache.set(transcriptionDocId, content);
        }

        // Also update ContentContext if available
        if (contentContext.current) {
          contentContext.current.updateDocumentContent(
            transcriptionDocId,
            content
          );
        }
      }

      const hasContent = !!content && content.trim().length > 0;
      console.log(
        `[TRANSCRIPTION] Content from API: ${
          hasContent ? "Not empty" : "Empty"
        }`
      );
      return hasContent;
    } catch (error) {
      console.error(`[TRANSCRIPTION] Error in direct API fetch:`, error);
      return false;
    }
  }, [transcriptionDocId]);

  // Wrap startRecording to update EncuentroContext state
  const startRecording = useCallback(() => {
    // First call the original startRecording
    voiceRecorder.startRecording();
  }, [voiceRecorder.startRecording]);

  // Wrap stopRecording to handle EncuentroContext updates
  const stopRecording = useCallback(() => {
    voiceRecorder.stopRecording();
    console.log("SETTING HAS_BEEN_TRANSCRIBED TO FALSE");
    // Now set has_been_transcribed to false once new audio finishes uploading
    updateEncuentro({ has_been_transcribed: false }).catch((error) =>
      console.error(
        "[TRANSCRIPTION] Error updating has_been_transcribed:",
        error
      )
    );
    console.log(
      `[TRANSCRIPTION][STOP] Setting hasBeenTranscribed from ${hasBeenTranscribed} to false, source: stopRecording`
    );
    setHasBeenTranscribed(false);
  }, [voiceRecorder, updateEncuentro, hasBeenTranscribed]);

  // Wrap deleteRecording to handle EncuentroContext updates
  const deleteRecording = useCallback(async () => {
    // Just call the original deleteRecording without changing has_been_transcribed
    await voiceRecorder.deleteRecording();

    // We don't update has_been_transcribed when deleting
  }, [voiceRecorder.deleteRecording]);

  // Create the combined context value
  const value: TranscriptionContextType = {
    // State from voice recorder
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

    // State from local state management instead of transcription hook
    isTranscribing,
    transcriptionStatus,
    errorMessage,

    // Audio recording actions from voice recorder - use wrapped versions
    startRecording,
    stopRecording,
    pauseResumeRecording: voiceRecorder.pauseResumeRecording,
    deleteRecording,

    // Transcription actions
    transcribeAudio,
    resetTranscriptionState,
    setHasBeenTranscribed: loggedSetHasBeenTranscribed,
    onTranscriptionComplete: handleTranscriptionComplete,
    checkTranscriptionContent,
  };

  useEffect(() => {
    console.log(
      `[TRANSCRIPTION][EFFECT] hasBeenTranscribed changed to: ${hasBeenTranscribed}`
    );
    return () => {
      console.log(
        `[TRANSCRIPTION][CLEANUP] Last value of hasBeenTranscribed before cleanup: ${hasBeenTranscribed}`
      );
    };
  }, [hasBeenTranscribed]);

  // Fix the problematic effect by removing hasBeenTranscribed from dependencies
  // and adding a conditional check to prevent unnecessary updates
  useEffect(() => {
    if (encuentro && encuentro.has_been_transcribed !== undefined) {
      // Only update if the value is different to avoid loops
      if (!!encuentro.has_been_transcribed !== hasBeenTranscribed) {
        console.log(
          `[TRANSCRIPTION][INIT] Setting hasBeenTranscribed from ${hasBeenTranscribed} to ${!!encuentro.has_been_transcribed}, source: encuentro data`
        );
        setHasBeenTranscribed(!!encuentro.has_been_transcribed);
      }
    }
  }, [encuentro]); // Remove hasBeenTranscribed from dependencies

  // --- Effect to Reset State on encounterId Change ---
  useEffect(() => {
    console.log(`[TRANSCRIPTION][EFFECT_ENCOUNTER] Encounter ID changed to: ${encounterId}. Initial mount: ${isInitialMount.current}`);

    if (isInitialMount.current) {
      isInitialMount.current = false;
      // Initial setup based on props is handled by useState and the effect syncing with `encuentro`
      console.log(`[TRANSCRIPTION][EFFECT_ENCOUNTER] Initial mount for ${encounterId}. Skipping reset.`);
      // Ensure initial doc ID is set if provided
      if (initialTranscriptionDocId !== transcriptionDocId) {
         setTranscriptionDocId(initialTranscriptionDocId);
      }
      return;
    }

    // Reset logic for subsequent encounter changes or invalid encounterId
    console.log(`[TRANSCRIPTION][EFFECT_ENCOUNTER] Resetting state due to encounter change to ${encounterId}.`);

    // 1. Close existing SSE connection
    if (eventSourceRef.current) {
      console.log("[TRANSCRIPTION][RESET] Closing existing SSE connection.");
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    // 2. Reset transcription status states
    setIsTranscribing(false);
    setTranscriptionStatus("idle");
    setErrorMessage(null);
    setTranscriptionCompleteTimestamp(null);

    // 3. Reset transcriptionDocId based on new initial prop
    setTranscriptionDocId(initialTranscriptionDocId ?? null);

    // 4. Reset hasBeenTranscribed (the effect below will sync with the new encounter data)
    console.log(`[TRANSCRIPTION][RESET] Setting hasBeenTranscribed to false temporarily.`);
    setHasBeenTranscribed(false);

    // 5. Reset voice recorder state implicitly
    // The useVoiceRecorder hook depends on transcriptionDocId.
    // Since we updated transcriptionDocId above, the hook should re-run its internal logic
    // to check audio existence etc. for the new document ID (or null).
    console.log(`[TRANSCRIPTION][RESET] Relying on useVoiceRecorder to update based on new transcriptionDocId: ${initialTranscriptionDocId ?? null}`);


  }, [encounterId, initialTranscriptionDocId]); // Dependencies: Run when encounter or its initial doc ID changes

  return (
    <TranscriptionContext.Provider value={value}>
      {children}
    </TranscriptionContext.Provider>
  );
}

// Custom hook
export function useTranscriptionContext() {
  const context = useContext(TranscriptionContext);
  if (context === undefined) {
    throw new Error(
      "useTranscriptionContext must be used within a TranscriptionProvider"
    );
  }
  return context;
}

// Add type for global document content cache
declare global {
  interface Window {
    documentContentCache?: Map<number, string>;
  }
}
