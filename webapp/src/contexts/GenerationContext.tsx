import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { useDocumentContext } from "./DocumentContext";
import { useContentContext } from "./ContentContext";
import { useTranscriptionContext } from "./TranscriptionContext"; // Add this import
import { logger } from "@/lib/logger";

const API_URL = import.meta.env.VITE_API_URL;

// Types from useDocumentGeneration.tsx
interface GenerationStatus {
  inProgress: boolean;
  processingId: string | null;
  documentId: number | null;
  content: string;
  error: string | null;
  isComplete: boolean;
}

interface Plantilla {
  id: number;
  name: string;
  document_kind: string;
  created_at: string;
  is_base: boolean;
  use_count: number;
  last_used_at: string | null;
}

// Define the context type
type GenerationContextType = {
  // Modal state
  isModalOpen: boolean;
  openGenerationModal: () => void;
  closeGenerationModal: () => void;

  // Generation state
  isGenerating: boolean;
  error: string | null;
  generationStatus: GenerationStatus;

  // Plantilla state
  plantillas: Plantilla[];
  isLoadingPlantillas: boolean;
  plantillasError: string | null;
  selectedPlantillaId: number | null;
  setSelectedPlantillaId: (id: number | null) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;

  // Actions
  generateDocumentation: () => Promise<any>;
  fetchPlantillas: () => Promise<void>;
};

// Create the context
const GenerationContext = createContext<GenerationContextType | undefined>(
  undefined
);

// Create the provider
export function GenerationProvider({
  children,
  encounterId,
}: {
  children: React.ReactNode;
  encounterId: number;
}) {
  const { documents, addDocument, saveDocument, selectDocument } =
    useDocumentContext();
  const { updateDocumentContent } = useContentContext();
  const { hasBeenTranscribed } = useTranscriptionContext(); // Add this line to get transcription status

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  // Generation state
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Template state
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [isLoadingPlantillas, setIsLoadingPlantillas] =
    useState<boolean>(false);
  const [plantillasError, setPlantillasError] = useState<string | null>(null);
  const [selectedPlantillaId, setSelectedPlantillaId] = useState<number | null>(
    null
  );
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Generation status
  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>({
    inProgress: false,
    processingId: null,
    documentId: null,
    content: "",
    error: null,
    isComplete: false,
  });

  // SSE connection reference
  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup SSE connection when component unmounts
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Fetch plantillas when modal opens
  useEffect(() => {
    if (isModalOpen) {
      fetchPlantillas();
    }
  }, [isModalOpen]);

  const fetchPlantillas = useCallback(async () => {
    try {
      setIsLoadingPlantillas(true);
      setPlantillasError(null);

      const response = await axiosInstance.get("/api/doctor-templates/short");
      setPlantillas(response.data || []);

      // Select first template by default if available
      if (response.data && response.data.length > 0) {
        setSelectedPlantillaId(response.data[0].id);
      }
    } catch (err) {
      logger.error("❌ Error al cargar plantillas:", err);
      setPlantillasError("No se pudieron cargar las plantillas");
    } finally {
      setIsLoadingPlantillas(false);
    }
  }, []);

  const openGenerationModal = useCallback(() => {
    setIsModalOpen(true);
    setError(null);
  }, []);

  const closeGenerationModal = useCallback(() => {
    setIsModalOpen(false);
    setSearchQuery("");
  }, []);

  const createNewDocument = useCallback(async () => {
    try {
      // Call API to create new empty document of type "nota"
      const response = await axiosInstance.post("/api/documents", {
        encounter_id: encounterId,
        kind: "note",
      });

      logger.debug("📄 Documento nuevo creado:", response.data);

      // Call the callback with the new document
      if (addDocument && response.data) {
        addDocument(response.data);
      }

      return response.data;
    } catch (err) {
      logger.error("❌ Error al crear nuevo documento:", err);
      throw err;
    }
  }, [encounterId, addDocument]);

  const getSSEToken = useCallback(async (documentId: number) => {
    try {
      const response = await axiosInstance.post(
        `/api/generate-sse-token/${documentId}`
      );

      if (response.data.success && response.data.token) {
        return response.data.token as string;
      }

      logger.error(
        "❌ Failed to get SSE token for generation:",
        response.data.error
      );
      return null;
    } catch (err) {
      logger.error("❌ Error getting SSE token for generation:", err);
      return null;
    }
  }, []);

  // Connect to SSE with token
  const connectToSSE = useCallback(
    (documentId: number, sseToken: string) => {
      // Close any existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      // Create full URL to the SSE endpoint with secure token using API URL from env
      const apiBaseUrl = API_URL.endsWith("/") ? API_URL.slice(0, -1) : API_URL;
      const sseUrl = `${apiBaseUrl}/api/sse/document/${documentId}/${sseToken}`;

      logger.debug(`🔌 Connecting to SSE endpoint: ${sseUrl}`);

      try {
        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          logger.debug(
            `✅ SSE connection established for document ${documentId}`
          );
        };

        eventSource.onmessage = async (event) => {
          try {
            const data = JSON.parse(event.data);
            logger.debug(`📩 SSE message received: ${data.event}`);

            switch (data.event) {
              case "connected":
                logger.debug(
                  "✅ Connected to SSE for document",
                  data.document_id
                );
                break;

              case "generation_chunk":
                const newChunk = data.chunk || "";

                setGenerationStatus((prev) => {
                  const updatedContent = prev.content + newChunk;

                  if (saveDocument && documentId && newChunk) {
                    saveDocument(documentId, updatedContent).catch((err) =>
                      logger.error("Error saving document content:", err)
                    );
                  }

                  return {
                    ...prev,
                    content: updatedContent,
                    error: null,
                  };
                });
                break;

              case "generation_complete":
                // Use setGenerationStatus functional update to get the latest state reliably
                setGenerationStatus((prevStatus) => {
                  const finalContent = data.chunk || prevStatus.content;
                  const targetDocumentId = prevStatus.documentId; // Get ID from the latest state

                  logger.debug(
                    `✅ Generation complete - Target Doc ID: ${targetDocumentId}, Final content length: ${finalContent.length} chars`
                  );

                  // Save final content to database using the correct targetDocumentId
                  if (saveDocument && targetDocumentId) {
                    saveDocument(targetDocumentId, finalContent)
                      .then((saveSuccess) => {
                        logger.debug(
                          `📝 Final content saved to database (Doc ${targetDocumentId}, ${finalContent.length} chars), Success: ${saveSuccess}`
                        );

                        // IMPORTANT: Update ContentContext state AFTER successful save using the correct targetDocumentId
                        if (saveSuccess && updateDocumentContent) {
                          updateDocumentContent(targetDocumentId, finalContent); // Use correct targetDocumentId
                          logger.debug(
                            `🔄 Explicitly updated ContentContext state for document ${targetDocumentId}` // Log correct ID
                          );
                        }

                        // Force editor refresh AFTER state updates, keep the correct document selected
                        setTimeout(() => {
                          // Ensure the correct document remains selected
                          if (selectDocument && targetDocumentId) {
                            selectDocument(targetDocumentId); // Use correct targetDocumentId
                            logger.debug(
                              `🔄 Ensured document ${targetDocumentId} is selected to refresh UI` // Log correct ID
                            );
                          }
                          if (window.triggerEditorRefresh) {
                            window.triggerEditorRefresh();
                            logger.debug(`🔄 Triggered general editor refresh`);
                          }
                        }, 100); // Timeout allows state to propagate
                      })
                      .catch((err) => {
                        logger.error(
                          `❌ Error saving final content for Doc ${targetDocumentId}:`,
                          err
                        );
                      });
                  } else {
                    logger.warn(
                      `⚠️ Skipped final save/update for Doc ${targetDocumentId} (saveDocument or targetDocumentId missing)`
                    );
                  }

                  // Update local state after initiating save/update
                  return {
                    ...prevStatus,
                    content: finalContent,
                    isComplete: true,
                    inProgress: false,
                    error: null, // Clear error on success
                  };
                });

                // Move setIsGenerating outside setGenerationStatus
                setIsGenerating(false);
                setError(null); // Clear any previous generation error
                break;

              case "generation_error":
                setGenerationStatus((prev) => ({
                  ...prev,
                  error: data.error || "Error desconocido",
                  inProgress: false,
                }));
                setIsGenerating(false);
                setError(data.error || "Error en la generación");
                break;
            }
          } catch (err) {
            logger.error("❌ Error processing SSE message:", err);
            // Update status on error
            setGenerationStatus((prev) => ({
              ...prev,
              error: "Error al procesar el mensaje",
              inProgress: false,
            }));
            setIsGenerating(false);
            setError("Error al procesar el mensaje");
          }
        };

        eventSource.onerror = (err) => {
          logger.error("❌ SSE connection error:", err);
          setError("Error en la conexión con el servidor");

          // Close and cleanup on error
          eventSource.close();
          eventSourceRef.current = null;
        };

        return eventSource;
      } catch (error) {
        logger.error("Error creating SSE connection:", error);
        return null;
      }
    },
    // Update dependency array
    [saveDocument, updateDocumentContent, selectDocument, API_URL]
  );

  const generateDocumentation = useCallback(async () => {
    try {
      if (!selectedPlantillaId) {
        throw new Error("Por favor seleccione una plantilla");
      }

      setIsGenerating(true);
      setError(null);
      setGenerationStatus({
        inProgress: true,
        processingId: null,
        documentId: null,
        content: "",
        error: null,
        isComplete: false,
      });

      // Find transcription and context documents
      const transcriptionDoc = documents.find(
        (doc) => doc.kind === "transcription"
      );
      const contextDoc = documents.find((doc) => doc.kind === "context");

      if (!transcriptionDoc) {
        throw new Error("No se encontró el documento de transcripción");
      }

      if (!contextDoc) {
        throw new Error("No se encontró el documento de contexto");
      }

      // Check if transcription has been completed using the hasBeenTranscribed flag
      // instead of checking the document content
      if (!hasBeenTranscribed) {
        throw new Error(
          "Debe transcribir el audio antes de generar un documento"
        );
      }

      logger.debug("📄 Documents found:", {
        transcripcion: transcriptionDoc.id,
        contexto: contextDoc.id,
      });

      // Create new document for the generated content
      const newDocument = await createNewDocument();

      if (!newDocument || !newDocument.id) {
        throw new Error("Error al crear nuevo documento");
      }

      setGenerationStatus((prev) => ({
        ...prev,
        documentId: newDocument.id,
      }));

      if (selectDocument) {
        selectDocument(newDocument.id);
      }

      const sseToken = await getSSEToken(newDocument.id);
      if (!sseToken) {
        throw new Error(
          "No se pudo autenticar para las actualizaciones en tiempo real"
        );
      }

      connectToSSE(newDocument.id, sseToken);
      setIsModalOpen(false);

      // Request document generation workflow
      const response = await axiosInstance.post("/api/documents/generate", {
        context_document_id: contextDoc.id,
        transcription_document_id: transcriptionDoc.id,
        doctor_template_id: selectedPlantillaId,
        new_document_id: newDocument.id,
      });

      if (!response.data.success) {
        throw new Error(response.data.error || "Error al iniciar generación");
      }

      // Track template usage after successful generation request
      try {
        const usageResponse = await axiosInstance.post(
          `/api/doctor-templates/${selectedPlantillaId}/usage`
        );
        logger.debug("📊 Uso de plantilla registrado:", usageResponse.data);
      } catch (usageErr) {
        // Log error but don't interrupt the main flow
        logger.error("❌ Error al registrar uso de plantilla:", usageErr);
      }

      // Update generation status with info from response
      setGenerationStatus((prev) => ({
        ...prev,
        processingId: response.data.process_id,
      }));

      // Return the new document so it can be selected
      return newDocument;
    } catch (err) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      setError(err instanceof Error ? err.message : "Error desconocido");
      setIsGenerating(false);
      setGenerationStatus((prev) => ({
        ...prev,
        inProgress: false,
        error: err instanceof Error ? err.message : "Error desconocido",
      }));
      logger.error("❌ Error generando documentación:", err);
      return null;
    }
  }, [
    documents,
    createNewDocument,
    getSSEToken,
    selectedPlantillaId,
    connectToSSE,
    selectDocument,
    hasBeenTranscribed, // Add hasBeenTranscribed to the dependencies
  ]);

  // Filter plantillas based on search query
  const filteredPlantillas = searchQuery
    ? plantillas.filter((p) =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : plantillas;

  // Create the context value
  const value: GenerationContextType = {
    isModalOpen,
    openGenerationModal,
    closeGenerationModal,
    isGenerating,
    error,
    generationStatus,
    plantillas: filteredPlantillas,
    isLoadingPlantillas,
    plantillasError,
    selectedPlantillaId,
    setSelectedPlantillaId,
    searchQuery,
    setSearchQuery,
    generateDocumentation,
    fetchPlantillas,
  };

  return (
    <GenerationContext.Provider value={value}>
      {children}
    </GenerationContext.Provider>
  );
}

// Custom hook
export function useGenerationContext() {
  const context = useContext(GenerationContext);
  if (context === undefined) {
    throw new Error(
      "useGenerationContext must be used within a GenerationProvider"
    );
  }
  return context;
}
