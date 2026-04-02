import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { DocumentoOut } from "@/types/documento";
import { useDocumentContext } from "./DocumentContext";
import { useContentContext } from "./ContentContext";
import { useTranscriptionContext } from "./TranscriptionContext";
import { logger } from "@/lib/logger";

const API_URL = import.meta.env.VITE_API_URL;

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

type GenerationContextType = {
  isModalOpen: boolean;
  openGenerationModal: () => void;
  closeGenerationModal: () => void;

  isGenerating: boolean;
  error: string | null;
  generationStatus: GenerationStatus;

  plantillas: Plantilla[];
  isLoadingPlantillas: boolean;
  plantillasError: string | null;
  selectedPlantillaId: number | null;
  setSelectedPlantillaId: (id: number | null) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;

  generateDocumentation: () => Promise<DocumentoOut | null>;
  fetchPlantillas: () => Promise<void>;
};

const GenerationContext = createContext<GenerationContextType | undefined>(
  undefined
);

export function GenerationProvider({
  children,
  encounterId,
}: {
  children: React.ReactNode;
  encounterId: number;
}) {
  const { documents, addDocument, selectDocument } = useDocumentContext();
  const { updateDocumentContent } = useContentContext();
  const { hasBeenTranscribed } = useTranscriptionContext();

  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [isLoadingPlantillas, setIsLoadingPlantillas] =
    useState<boolean>(false);
  const [plantillasError, setPlantillasError] = useState<string | null>(null);
  const [selectedPlantillaId, setSelectedPlantillaId] = useState<number | null>(
    null
  );
  const [searchQuery, setSearchQuery] = useState<string>("");

  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>({
    inProgress: false,
    processingId: null,
    documentId: null,
    content: "",
    error: null,
    isComplete: false,
  });

  // Generation owns its SSE lifecycle so encounter detail keeps a single
  // long-lived source of truth for streaming state and side effects.
  const eventSourceRef = useRef<EventSource | null>(null);
  const streamedContentRef = useRef("");
  const streamingDocumentIdRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const fetchPlantillas = useCallback(async () => {
    try {
      setIsLoadingPlantillas(true);
      setPlantillasError(null);

      const response = await axiosInstance.get("/api/doctor-templates/short");
      setPlantillas(response.data || []);

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

  useEffect(() => {
    if (isModalOpen) {
      void fetchPlantillas();
    }
  }, [fetchPlantillas, isModalOpen]);

  const openGenerationModal = useCallback(() => {
    setIsModalOpen(true);
    setError(null);
  }, []);

  const closeGenerationModal = useCallback(() => {
    setIsModalOpen(false);
    setSearchQuery("");
  }, []);

  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const createNewDocument = useCallback(async () => {
    try {
      const response = await axiosInstance.post("/api/documents", {
        encounter_id: encounterId,
        kind: "note",
      });

      logger.debug("📄 Documento nuevo creado:", response.data);

      if (addDocument && response.data) {
        queueMicrotask(() => {
          addDocument(response.data);
        });
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

  const connectToSSE = useCallback(
    (documentId: number, sseToken: string) => {
      closeEventSource();

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

              case "generation_chunk": {
                const newChunk = data.chunk || "";
                const updatedContent = streamedContentRef.current + newChunk;

                streamedContentRef.current = updatedContent;
                updateDocumentContent(documentId, updatedContent);
                setGenerationStatus((prev) => ({
                  ...prev,
                  content: updatedContent,
                  error: null,
                }));
                break;
              }

              case "generation_complete": {
                const targetDocumentId =
                  streamingDocumentIdRef.current ?? documentId;
                const finalContent = data.chunk || streamedContentRef.current;

                logger.debug(
                  `✅ Generation complete - Target Doc ID: ${targetDocumentId}, Final content length: ${finalContent.length} chars`
                );

                streamedContentRef.current = finalContent;
                if (targetDocumentId) {
                  updateDocumentContent(targetDocumentId, finalContent);
                }
                setGenerationStatus((prevStatus) => ({
                  ...prevStatus,
                  documentId: targetDocumentId,
                  content: finalContent,
                  isComplete: true,
                  inProgress: false,
                  error: null,
                }));
                setIsGenerating(false);
                setError(null);
                closeEventSource();
                break;
              }

              case "generation_error":
                setGenerationStatus((prev) => ({
                  ...prev,
                  error: data.error || "Error desconocido",
                  inProgress: false,
                }));
                setIsGenerating(false);
                setError(data.error || "Error en la generación");
                closeEventSource();
                break;
            }
          } catch (err) {
            logger.error("❌ Error processing SSE message:", err);
            setGenerationStatus((prev) => ({
              ...prev,
              error: "Error al procesar el mensaje",
              inProgress: false,
            }));
            setIsGenerating(false);
            setError("Error al procesar el mensaje");
            closeEventSource();
          }
        };

        eventSource.onerror = (err) => {
          logger.error("❌ SSE connection error:", err);
          setError("Error en la conexión con el servidor");

          closeEventSource();
        };

        return eventSource;
      } catch (error) {
        logger.error("Error creating SSE connection:", error);
        return null;
      }
    },
    [closeEventSource, updateDocumentContent]
  );

  const generateDocumentation = useCallback(async () => {
    try {
      if (!selectedPlantillaId) {
        throw new Error("Por favor seleccione una plantilla");
      }

      setIsGenerating(true);
      setError(null);
      streamedContentRef.current = "";
      streamingDocumentIdRef.current = null;
      setGenerationStatus({
        inProgress: true,
        processingId: null,
        documentId: null,
        content: "",
        error: null,
        isComplete: false,
      });

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

      if (!hasBeenTranscribed) {
        throw new Error(
          "Debe transcribir el audio antes de generar un documento"
        );
      }

      logger.debug("📄 Documents found:", {
        transcripcion: transcriptionDoc.id,
        contexto: contextDoc.id,
      });

      const newDocument = await createNewDocument();

      if (!newDocument || !newDocument.id) {
        throw new Error("Error al crear nuevo documento");
      }

      setGenerationStatus((prev) => ({
        ...prev,
        documentId: newDocument.id,
      }));
      streamingDocumentIdRef.current = newDocument.id;

      if (selectDocument) {
        // Selection stays under context control while chunks stream into the
        // new note, so feature components do not need their own generation state.
        queueMicrotask(() => {
          selectDocument(newDocument.id);
        });
      }

      const sseToken = await getSSEToken(newDocument.id);
      if (!sseToken) {
        throw new Error(
          "No se pudo autenticar para las actualizaciones en tiempo real"
        );
      }

      connectToSSE(newDocument.id, sseToken);
      setIsModalOpen(false);

      const response = await axiosInstance.post("/api/documents/generate", {
        context_document_id: contextDoc.id,
        transcription_document_id: transcriptionDoc.id,
        doctor_template_id: selectedPlantillaId,
        new_document_id: newDocument.id,
      });

      if (!response.data.success) {
        throw new Error(response.data.error || "Error al iniciar generación");
      }

      try {
        const usageResponse = await axiosInstance.post(
          `/api/doctor-templates/${selectedPlantillaId}/usage`
        );
        logger.debug("📊 Uso de plantilla registrado:", usageResponse.data);
      } catch (usageErr) {
        logger.error("❌ Error al registrar uso de plantilla:", usageErr);
      }

      setGenerationStatus((prev) => ({
        ...prev,
        processingId: response.data.process_id,
      }));

      return newDocument;
    } catch (err) {
      closeEventSource();

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
    closeEventSource,
    selectDocument,
    hasBeenTranscribed,
  ]);

  const filteredPlantillas = searchQuery
    ? plantillas.filter((p) =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : plantillas;

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

export function useGenerationContext() {
  const context = useContext(GenerationContext);
  if (context === undefined) {
    throw new Error(
      "useGenerationContext must be used within a GenerationProvider"
    );
  }
  return context;
}
