import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from "react";
import axiosInstance from "@/commons/utils/axiosInstance";
import { DocumentoOut } from "@/types/documento";
import { useDocumentContext } from "./DocumentContext";
import { useContentContext } from "./ContentContext";
import { useTranscriptionContext } from "./TranscriptionContext";
import { logger } from "@/lib/logger";
import { useDocumentDerivedStore } from "@/workspace/stores/documentDerivedStore";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";

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
}: {
  children: React.ReactNode;
  encounterId: number;
}) {
  const { documents, createDocument } = useDocumentContext();
  const { fetchDocumentContent, updateDocumentContent } = useContentContext();
  const { hasBeenTranscribed } = useTranscriptionContext();

  const activeGenerationDocumentId = useDocumentDerivedStore(
    (state) => state.activeGenerationDocumentId
  );
  const derivedByDocumentId = useDocumentDerivedStore(
    (state) => state.derivedByDocumentId
  );
  const startGeneration = useDocumentDerivedStore(
    (state) => state.startGeneration
  );
  const setGenerationProcessingId = useDocumentDerivedStore(
    (state) => state.setGenerationProcessingId
  );
  const updateGenerationContent = useDocumentDerivedStore(
    (state) => state.updateGenerationContent
  );
  const completeGeneration = useDocumentDerivedStore(
    (state) => state.completeGeneration
  );
  const failGeneration = useDocumentDerivedStore(
    (state) => state.failGeneration
  );
  const clearDocumentDerivedState = useDocumentDerivedStore(
    (state) => state.clearDocumentDerivedState
  );
  const resetDraftFromSnapshot = useDocumentDraftStore(
    (state) => state.resetDraftFromSnapshot
  );
  const markDraftClean = useDocumentDraftStore((state) => state.markDraftClean);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [isLoadingPlantillas, setIsLoadingPlantillas] = useState(false);
  const [plantillasError, setPlantillasError] = useState<string | null>(null);
  const [selectedPlantillaId, setSelectedPlantillaId] = useState<number | null>(
    null
  );
  const [searchQuery, setSearchQuery] = useState("");

  const eventSourceRef = useRef<EventSource | null>(null);
  const streamedContentRef = useRef("");
  const streamingDocumentIdRef = useRef<number | null>(null);

  const generationDerivedState = activeGenerationDocumentId
    ? derivedByDocumentId[activeGenerationDocumentId] ?? null
    : null;

  const generationStatus = useMemo<GenerationStatus>(
    () => ({
      inProgress: Boolean(generationDerivedState?.inProgress),
      processingId: generationDerivedState?.processingId ?? null,
      documentId: activeGenerationDocumentId
        ? Number(activeGenerationDocumentId)
        : null,
      content: generationDerivedState?.streamingContent ?? "",
      error: generationDerivedState?.error ?? error,
      isComplete: Boolean(generationDerivedState?.isComplete),
    }),
    [activeGenerationDocumentId, error, generationDerivedState]
  );

  const isGenerating = generationStatus.inProgress;

  // Generation keeps the SSE connection here, but the state visible to the UI
  // now lives in DocumentDerivedStore so the editor has one consistent source.
  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      closeEventSource();
    };
  }, [closeEventSource]);

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

  const createNewDocument = useCallback(async () => {
    try {
      const newDocument = await createDocument("note");
      logger.debug("📄 Documento nuevo creado:", newDocument);
      return newDocument;
    } catch (err) {
      logger.error("❌ Error al crear nuevo documento:", err);
      throw err;
    }
  }, [createDocument]);

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
                return;

              case "generation_chunk": {
                const newChunk = data.chunk || "";
                const updatedContent = streamedContentRef.current + newChunk;
                streamedContentRef.current = updatedContent;
                updateGenerationContent(String(documentId), updatedContent);
                return;
              }

              case "generation_complete": {
                const targetDocumentId =
                  streamingDocumentIdRef.current ?? documentId;
                const finalContent = data.chunk || streamedContentRef.current;

                logger.debug(
                  `✅ Generation complete - Target Doc ID: ${targetDocumentId}, Final content length: ${finalContent.length} chars`
                );

                streamedContentRef.current = finalContent;
                const refreshedContent = await fetchDocumentContent(
                  targetDocumentId,
                  true,
                );
                if (refreshedContent === null) {
                  updateDocumentContent(targetDocumentId, finalContent);
                }
                resetDraftFromSnapshot(String(targetDocumentId));
                markDraftClean(String(targetDocumentId));
                completeGeneration(String(targetDocumentId), finalContent);
                setError(null);
                closeEventSource();
                return;
              }

              case "generation_error": {
                const message = data.error || "Error desconocido";
                failGeneration(String(documentId), message);
                setError(message);
                closeEventSource();
                return;
              }
            }
          } catch (err) {
            logger.error("❌ Error processing SSE message:", err);
            const message = "Error al procesar el mensaje";
            failGeneration(String(documentId), message);
            setError(message);
            closeEventSource();
          }
        };

        eventSource.onerror = (err) => {
          logger.error("❌ SSE connection error:", err);
          const message = "Error en la conexión con el servidor";
          failGeneration(String(documentId), message);
          setError(message);
          closeEventSource();
        };

        return eventSource;
      } catch (connectionError) {
        logger.error("Error creating SSE connection:", connectionError);
        return null;
      }
    },
    [
      closeEventSource,
      completeGeneration,
      failGeneration,
      fetchDocumentContent,
      markDraftClean,
      resetDraftFromSnapshot,
      updateDocumentContent,
      updateGenerationContent,
    ]
  );

  const generateDocumentation = useCallback(async () => {
    let createdDocumentId: number | null = null;

    try {
      if (!selectedPlantillaId) {
        throw new Error("Por favor seleccione una plantilla");
      }

      setError(null);
      streamedContentRef.current = "";
      streamingDocumentIdRef.current = null;

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
      if (!newDocument?.id) {
        throw new Error("Error al crear nuevo documento");
      }

      createdDocumentId = newDocument.id;
      streamingDocumentIdRef.current = newDocument.id;

      if (
        activeGenerationDocumentId &&
        activeGenerationDocumentId !== String(newDocument.id)
      ) {
        clearDocumentDerivedState(activeGenerationDocumentId);
      }

      startGeneration(String(newDocument.id));
      updateDocumentContent(newDocument.id, "");
      resetDraftFromSnapshot(String(newDocument.id));
      markDraftClean(String(newDocument.id));

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

      setGenerationProcessingId(
        String(newDocument.id),
        response.data.process_id ?? null
      );

      try {
        const usageResponse = await axiosInstance.post(
          `/api/doctor-templates/${selectedPlantillaId}/usage`
        );
        logger.debug("📊 Uso de plantilla registrado:", usageResponse.data);
      } catch (usageErr) {
        logger.error("❌ Error al registrar uso de plantilla:", usageErr);
      }

      return newDocument;
    } catch (err) {
      closeEventSource();

      const message =
        err instanceof Error ? err.message : "Error desconocido";
      if (createdDocumentId) {
        failGeneration(String(createdDocumentId), message);
      }
      setError(message);
      logger.error("❌ Error generando documentación:", err);
      return null;
    }
  }, [
    activeGenerationDocumentId,
    clearDocumentDerivedState,
    closeEventSource,
    connectToSSE,
    createNewDocument,
    documents,
    failGeneration,
    getSSEToken,
    hasBeenTranscribed,
    markDraftClean,
    resetDraftFromSnapshot,
    selectedPlantillaId,
    setGenerationProcessingId,
    startGeneration,
    updateDocumentContent,
  ]);

  const filteredPlantillas = searchQuery
    ? plantillas.filter((plantilla) =>
        plantilla.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : plantillas;

  const value: GenerationContextType = {
    isModalOpen,
    openGenerationModal,
    closeGenerationModal,
    isGenerating,
    error: generationStatus.error,
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
