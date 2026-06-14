import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TabBar from "./TabBar/TabBar";
import TextArea from "./TextArea/TextArea";
import LoadingSpinner from "@/commons/components/LoadingSpinner";
import ErrorDisplay from "@/commons/components/ErrorDisplay";
import DocumentGenerationModal from "./DocumentGenerationModal";
import { DocumentGenerationProgress } from "./components/DocumentGenerationProgress";
import { useDocumentContext } from "../../contexts/DocumentContext";
import { useGenerationContext } from "../../contexts/GenerationContext";
import { logger } from "@/lib/logger";
import { useWorkspaceStore } from "@/workspace/stores/workspaceStore";
interface DocumentAreaProps {
  onTranscriptionDocumentFound?: (documentId: number) => void;
}

const DocumentArea: React.FC<DocumentAreaProps> = ({
  onTranscriptionDocumentFound,
}) => {
  const { loading, error, isSaving } = useDocumentContext();
  const documentOrder = useWorkspaceStore((state) => state.documentOrder);
  const documentsById = useWorkspaceStore((state) => state.documentsById);
  const activeDocumentId = useWorkspaceStore((state) => state.activeDocumentId);
  const setActiveDocument = useWorkspaceStore((state) => state.setActiveDocument);
  const documents = useMemo(
    () =>
      documentOrder
        .map((documentId) => documentsById[documentId])
        .filter(Boolean),
    [documentOrder, documentsById]
  );
  const [lingeringGenerationDocumentId, setLingeringGenerationDocumentId] =
    useState<number | null>(null);
  const previousGenerationSnapshotRef = useRef<{
    documentId: number | null;
    inProgress: boolean;
    isComplete: boolean;
  }>({
    documentId: null,
    inProgress: false,
    isComplete: false,
  });
  const lingeringClearTimerRef = useRef<number | null>(null);

  const {
    isModalOpen,
    closeGenerationModal,
    isGenerating,
    error: generationError,
    generationStatus,
    generateDocumentation,
    plantillas,
    isLoadingPlantillas,
    plantillasError,
    selectedPlantillaId,
    setSelectedPlantillaId,
    searchQuery,
    setSearchQuery,
  } = useGenerationContext();

  const transcriptionDocumentId = useMemo(() => {
    const transcriptionDoc = documents.find((doc) => doc.type === "transcription");
    return transcriptionDoc ? Number(transcriptionDoc.id) : null;
  }, [documents]);

  useEffect(() => {
    if (
      !loading &&
      transcriptionDocumentId !== null &&
      onTranscriptionDocumentFound
    ) {
      onTranscriptionDocumentFound(transcriptionDocumentId);
    }
  }, [loading, onTranscriptionDocumentFound, transcriptionDocumentId]);

  const handleSelectDocument = useCallback(
    (docId: number) => {
      setActiveDocument(String(docId));
    },
    [setActiveDocument]
  );

  const handleExecuteGeneration = useCallback(async () => {
    try {
      return await generateDocumentation();
    } catch (error) {
      logger.error("Error generating documentation:", error);
      return null;
    }
  }, [generateDocumentation]);

  const generationTargetDocumentId = generationStatus.documentId;
  const shouldKeepGenerationPanelVisible =
    Boolean(generationStatus?.inProgress) ||
    lingeringGenerationDocumentId === generationTargetDocumentId;

  useEffect(() => {
    const previousSnapshot = previousGenerationSnapshotRef.current;
    const justCompleted =
      previousSnapshot.documentId === generationTargetDocumentId &&
      previousSnapshot.inProgress &&
      generationStatus.isComplete;

    logger.debug("[GENERATION_PANEL] Completion transition check", {
      previousDocumentId: previousSnapshot.documentId,
      previousInProgress: previousSnapshot.inProgress,
      previousIsComplete: previousSnapshot.isComplete,
      currentDocumentId: generationTargetDocumentId,
      currentInProgress: generationStatus.inProgress,
      currentIsComplete: generationStatus.isComplete,
      activeDocumentId,
      lingeringGenerationDocumentId,
      justCompleted,
    });

    previousGenerationSnapshotRef.current = {
      documentId: generationTargetDocumentId,
      inProgress: generationStatus.inProgress,
      isComplete: generationStatus.isComplete,
    };

    if (
      !justCompleted ||
      !generationTargetDocumentId ||
      activeDocumentId === String(generationTargetDocumentId)
    ) {
      logger.debug("[GENERATION_PANEL] Completion linger not scheduled", {
        generationTargetDocumentId,
        activeDocumentId,
        justCompleted,
      });
      return;
    }

    if (lingeringClearTimerRef.current !== null) {
      logger.debug("[GENERATION_PANEL] Clearing previous completion linger timer", {
        generationTargetDocumentId,
      });
      window.clearTimeout(lingeringClearTimerRef.current);
      lingeringClearTimerRef.current = null;
    }

    logger.debug("[GENERATION_PANEL] Scheduling completion linger", {
      generationTargetDocumentId,
      activeDocumentId,
    });
    setLingeringGenerationDocumentId(generationTargetDocumentId);
    lingeringClearTimerRef.current = window.setTimeout(() => {
      logger.debug("[GENERATION_PANEL] Clearing completion linger", {
        generationTargetDocumentId,
      });
      setLingeringGenerationDocumentId((current) =>
        current === generationTargetDocumentId ? null : current
      );
      lingeringClearTimerRef.current = null;
    }, 2000);
  }, [
    activeDocumentId,
    generationStatus.inProgress,
    generationStatus.isComplete,
    generationTargetDocumentId,
  ]);

  useEffect(() => {
    return () => {
      if (lingeringClearTimerRef.current !== null) {
        logger.debug("[GENERATION_PANEL] Cancelling completion linger timer on unmount");
        window.clearTimeout(lingeringClearTimerRef.current);
        lingeringClearTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    logger.debug("[GENERATION_PANEL] Visibility state", {
      activeDocumentId,
      generationTargetDocumentId,
      inProgress: generationStatus.inProgress,
      isComplete: generationStatus.isComplete,
      hasError: Boolean(generationStatus.error),
      lingeringGenerationDocumentId,
      shouldKeepGenerationPanelVisible,
      willRenderPanel:
        !isModalOpen &&
        shouldKeepGenerationPanelVisible &&
        activeDocumentId !== String(generationTargetDocumentId),
    });
  }, [
    activeDocumentId,
    generationStatus.error,
    generationStatus.inProgress,
    generationStatus.isComplete,
    generationTargetDocumentId,
    isModalOpen,
    lingeringGenerationDocumentId,
    shouldKeepGenerationPanelVisible,
  ]);

  // Loading state
  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <div className="bg-gray-100 p-2 border-b text-sm text-gray-500">
          Cargando documentos…
        </div>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner />
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col h-full">
        <div className="bg-gray-100 p-2 border-b text-sm text-gray-500">
          Error al cargar documentos
        </div>
        <div className="flex-1">
          <ErrorDisplay
            message="No se pudieron cargar los documentos"
            details={error}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full border rounded-md overflow-hidden">
      <TabBar />

      <div className="flex-1 overflow-auto bg-white">
        {documents.length > 0 ? (
          <TextArea />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            No hay documentos para este encuentro
          </div>
        )}
      </div>

      {/* Display real-time generation progress */}
      {!isModalOpen &&
        shouldKeepGenerationPanelVisible &&
        activeDocumentId !== String(generationTargetDocumentId) && (
          <div className="p-4 bg-white border-t">
            <DocumentGenerationProgress
              isGenerating={generationStatus.inProgress}
              content={generationStatus.content}
              isComplete={generationStatus.isComplete}
              error={generationStatus.error}
              pipelineStep={generationStatus.pipelineStep}
              pipelineMessage={generationStatus.pipelineMessage}
              onViewDocument={
                generationTargetDocumentId
                  ? () => handleSelectDocument(generationTargetDocumentId)
                  : undefined
              }
            />
          </div>
        )}

      {/* Saving indicator */}
      {isSaving && (
        <div className="bg-blue-50 text-blue-600 text-xs p-1 border-t text-center">
          Guardando cambios…
        </div>
      )}

      {/* Document Generation Modal */}
      <DocumentGenerationModal
        isOpen={isModalOpen}
        onClose={closeGenerationModal}
        onGenerate={handleExecuteGeneration}
        isGenerating={isGenerating}
        error={generationError}
        plantillas={plantillas}
        isLoadingPlantillas={isLoadingPlantillas}
        plantillasError={plantillasError}
        selectedPlantillaId={selectedPlantillaId}
        setSelectedPlantillaId={setSelectedPlantillaId}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        generationStatus={generationStatus}
      />
    </div>
  );
};

export default DocumentArea;
