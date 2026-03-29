import { useState, useCallback, useEffect, useRef } from "react";
import { DocumentoOut } from "@/types/documento";
import axiosInstance from "@/commons/utils/axiosInstance";
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
  nombre: string;
  tipo_documento: string;
  fecha_creacion: string;
  es_base: boolean;
  veces_usada: number;
  ultimo_uso: string | null;
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

      const response = await axiosInstance.get("/api/plantillas_short");
      setPlantillas(response.data || []);

      // Select first template by default if available
      if (response.data && response.data.length > 0) {
        setSelectedPlantillaId(response.data[0].id);
      }
    } catch (err) {
      console.error("❌ Error al cargar plantillas:", err);
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
      const response = await axiosInstance.post("/api/documento", {
        id_encuentro: encounterId,
        tipo: "nota",
      });

      console.log("📄 Documento nuevo creado:", response.data);

      // Call the callback with the new document
      if (onDocumentCreated && response.data) {
        onDocumentCreated(response.data);
      }

      return response.data;
    } catch (err) {
      console.error("❌ Error al crear nuevo documento:", err);
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
      const sseUrl = `${apiBaseUrl}/api/sse/documento/${documentId}/${sseToken}`;

      console.log(`🔌 Connecting to SSE endpoint: ${sseUrl}`);

      try {
        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          console.log(
            `✅ SSE connection established for document ${documentId}`
          );
        };

        eventSource.onmessage = async (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log(`📩 SSE message received: ${data.event}`);

            switch (data.event) {
              case "connected":
                console.log(
                  "✅ Connected to SSE for document",
                  data.id_documento
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
                      console.error("Error saving document content:", err)
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
                const finalContent = data.chunk || generationStatus.content;

                console.log(
                  `✅ Generation complete - Final content length: ${finalContent.length} chars`
                );

                // CRITICAL: Update the document content cache directly to prevent race condition
                if (window.documentContentCache && documentId) {
                  window.documentContentCache.set(documentId, finalContent);
                  console.log(
                    `💾 Manually updated cache for document ${documentId} with ${finalContent.length} chars`
                  );
                }

                // Save final content to database
                if (onContentUpdate && documentId) {
                  try {
                    await onContentUpdate(documentId, finalContent);
                    console.log(
                      `📝 Final content saved to database (${finalContent.length} chars)`
                    );
                  } catch (err) {
                    console.error("❌ Error saving final content:", err);
                  }
                }

                // Only after saving content, update the state
                setGenerationStatus((prev) => ({
                  ...prev,
                  content: finalContent,
                  isComplete: true,
                  inProgress: false,
                }));

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
            console.error("❌ Error processing SSE message:", err);
          }
        };

        eventSource.onerror = (err) => {
          console.error("❌ SSE connection error:", err);
          setError("Error en la conexión con el servidor");

          // Close and cleanup on error
          eventSource.close();
          eventSourceRef.current = null;
        };

        return eventSource;
      } catch (error) {
        console.error("Error creating SSE connection:", error);
        return null;
      }
    },
    [onContentUpdate, generationStatus.content]
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
        (doc) => doc.tipo === "transcripcion"
      );
      const contextDoc = documents.find((doc) => doc.tipo === "contexto");

      if (!transcriptionDoc) {
        throw new Error("No se encontró el documento de transcripción");
      }

      if (!contextDoc) {
        throw new Error("No se encontró el documento de contexto");
      }

      // Check if transcription content is empty
      if (
        !transcriptionDoc.contenido ||
        transcriptionDoc.contenido.trim() === ""
      ) {
        throw new Error(
          "You must perform the transcription before generating a document"
        );
      }

      console.log("📄 Documentos encontrados:", {
        transcripcion: transcriptionDoc.id,
        contexto: contextDoc.id,
      });

      // Create new document for the generated content
      const newDocument = await createNewDocument();

      if (!newDocument || !newDocument.id) {
        throw new Error("Error al crear nuevo documento");
      }

      // Request document generation workflow
      const response = await axiosInstance.post("/api/generate-document", {
        id_documento_contexto: contextDoc.id,
        id_documento_transcripcion: transcriptionDoc.id,
        id_plantilla_doctor: selectedPlantillaId,
        id_documento_nuevo: newDocument.id,
      });

      if (!response.data.success) {
        throw new Error(response.data.error || "Error al iniciar generación");
      }

      // Track template usage after successful generation request
      try {
        const usageResponse = await axiosInstance.post(
          `/api/plantilla_doctor/uso/${selectedPlantillaId}`
        );
        console.log("📊 Uso de plantilla registrado:", usageResponse.data);
      } catch (usageErr) {
        // Log error but don't interrupt the main flow
        console.error("❌ Error al registrar uso de plantilla:", usageErr);
      }

      // Update generation status with info from response
      setGenerationStatus((prev) => ({
        ...prev,
        processingId: response.data.id_proceso,
        documentId: newDocument.id, // Use the document ID from newDocument
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
      console.error("❌ Error generando documentación:", err);
      return null;
    }
  }, [documents, createNewDocument, selectedPlantillaId, connectToSSE]);

  // Filter plantillas based on search query
  const filteredPlantillas = searchQuery
    ? plantillas.filter((p) =>
        p.nombre.toLowerCase().includes(searchQuery.toLowerCase())
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
