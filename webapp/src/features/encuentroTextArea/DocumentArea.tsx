import React, { useCallback, useEffect } from "react";
import TabBar from "./TabBar/TabBar";
import TextArea from "./TextArea/TextArea";
import LoadingSpinner from "@/commons/components/LoadingSpinner";
import ErrorDisplay from "@/commons/components/ErrorDisplay";
import DocumentGenerationModal from "./DocumentGenerationModal";
import { DocumentGenerationProgress } from "./components/DocumentGenerationProgress";

// Import the context hooks
import { useDocumentContext } from "../../contexts/DocumentContext";
import { useGenerationContext } from "../../contexts/GenerationContext";
import { logger } from "@/lib/logger";
interface DocumentAreaProps {
  onTranscriptionDocumentFound?: (documentId: number) => void;
}

const DocumentArea: React.FC<DocumentAreaProps> = ({
  onTranscriptionDocumentFound,
}) => {
  // Get state from contexts instead of props
  const {
    documents,
    activeDocumentId,
    loading,
    error,
    isSaving,
    selectDocument,
  } = useDocumentContext();

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

  // Find and emit transcription document ID when documents load
  useEffect(() => {
    if (!loading && documents.length > 0 && onTranscriptionDocumentFound) {
      const transcriptionDoc = documents.find(
        (doc) => doc.kind === "transcription"
      );
      if (transcriptionDoc) {
        onTranscriptionDocumentFound(transcriptionDoc.id);
      }
    }
  }, [documents, loading, onTranscriptionDocumentFound]);

  // Handle document selection
  const handleSelectDocument = useCallback(
    (docId: number) => {
      selectDocument(docId);
    },
    [selectDocument]
  );

  // Handle document generation
  const handleExecuteGeneration = useCallback(async () => {
    try {
      return await generateDocumentation();
    } catch (error) {
      logger.error("Error generating documentation:", error);
      return null;
    }
  }, [generateDocumentation]);

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
        generationStatus?.inProgress &&
        activeDocumentId !== generationStatus.documentId && (
          <div className="p-4 bg-white border-t">
            <DocumentGenerationProgress
              isGenerating={generationStatus.inProgress}
              content={generationStatus.content}
              isComplete={generationStatus.isComplete}
              error={generationStatus.error}
              onViewDocument={
                generationStatus.documentId
                  ? () => handleSelectDocument(generationStatus.documentId!)
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
