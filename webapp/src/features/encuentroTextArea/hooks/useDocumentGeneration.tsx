import { useState, useCallback, useEffect, useRef } from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/commons/utils/axiosInstance";
import { logger } from "@/lib/logger";
const API_URL = import.meta.env.VITE_API_URL;

// Add types for generation status tracking
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

interface UseDocumentGenerationProps {
  documents: DocumentoOut[];
  encounterId: number;
  onDocumentCreated?: (newDocument: DocumentoOut) => void;
  onContentUpdate?: (documentId: number, content: string) => Promise<void>;
}

export function useDocumentGeneration({
  documents,
  encounterId,
  onDocumentCreated,
  onContentUpdate,
}: UseDocumentGenerationProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Template related state
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [isLoadingPlantillas, setIsLoadingPlantillas] = useState(false);
  const [plantillasError, setPlantillasError] = useState<string | null>(null);
  const [selectedPlantillaId, setSelectedPlantillaId] = useState<number | null>(
    null
  );
  const [searchQuery, setSearchQuery] = useState("");

  // New state for generation status
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
      if (onDocumentCreated && response.data) {
        onDocumentCreated(response.data);
      }

      return response.data;
    } catch (err) {
      logger.error("❌ Error al crear nuevo documento:", err);
      throw err;
    }
  }, [encounterId, onDocumentCreated]);

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

                  // Save content to document
                  if (onContentUpdate && documentId && newChunk) {
                    // Use the full accumulated content for saving
                    onContentUpdate(documentId, updatedContent).catch((err) =>
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
                setGenerationStatus((prev) => {
                  const finalContent =
                    data.chunk != null && String(data.chunk).length > 0
                      ? data.chunk
                      : prev.content;

                  logger.debug(
                    `✅ Generation complete - Final content length: ${finalContent.length} chars`
                  );

                  if (window.documentContentCache && documentId) {
                    window.documentContentCache.set(documentId, finalContent);
                    logger.debug(
                      `💾 Manually updated cache for document ${documentId} with ${finalContent.length} chars`
                    );
                  }

                  if (onContentUpdate && documentId) {
                    void onContentUpdate(documentId, finalContent)
                      .then(() =>
                        logger.debug(
                          `📝 Final content saved to database (${finalContent.length} chars)`
                        )
                      )
                      .catch((err) =>
                        logger.error("❌ Error saving final content:", err)
                      );
                  }

                  return {
                    ...prev,
                    content: finalContent,
                    isComplete: true,
                    inProgress: false,
                  };
                });

                setIsGenerating(false);
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
    [onContentUpdate]
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

      // Check if transcription content is empty
      if (
        !transcriptionDoc.content ||
        transcriptionDoc.content.trim() === ""
      ) {
        throw new Error(
          "Debe transcribir el audio antes de generar un documento"
        );
      }

      logger.debug("📄 Documentos encontrados:", {
        transcripcion: transcriptionDoc.id,
        contexto: contextDoc.id,
      });

      // Create new document for the generated content
      const newDocument = await createNewDocument();

      if (!newDocument || !newDocument.id) {
        throw new Error("Error al crear nuevo documento");
      }

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
        documentId: newDocument.id,
      }));

      // Connect to SSE for real-time updates
      connectToSSE(newDocument.id, response.data.sse_token);

      // Close the modal as generation has started
      setIsModalOpen(false);

      // Return the new document so it can be selected
      return newDocument;
    } catch (err) {
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
  }, [documents, createNewDocument, selectedPlantillaId, connectToSSE]);

  // Filter plantillas based on search query
  const filteredPlantillas = searchQuery
    ? plantillas.filter((p) =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : plantillas;

  return {
    isModalOpen,
    isGenerating,
    error,
    openGenerationModal,
    closeGenerationModal,
    generateDocumentation,
    plantillas: filteredPlantillas,
    isLoadingPlantillas,
    plantillasError,
    selectedPlantillaId,
    setSelectedPlantillaId,
    searchQuery,
    setSearchQuery,
    // New fields
    generationStatus,
  };
}
