import React, { useRef, useCallback } from "react";
import TabBar from "./TabBar/TabBar";
import TextArea from "./TextArea/TextArea";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorDisplay from "@/components/ErrorDisplay";
import { useDocuments } from "../../hooks/useDocuments";

interface DocumentAreaProps {
  encounterId: number;
}

const DocumentArea: React.FC<DocumentAreaProps> = ({ encounterId }) => {
  const {
    documents,
    activeDocument,
    activeDocumentId,
    loading,
    error,
    isSaving,
    selectDocument,
    saveDocument,
    // Extract these additional props from useDocuments
    documentContentCache,
    fetchDocumentContent,
    isLoadingContent,
  } = useDocuments(encounterId);

  // Reference to track the current editor's save function
  const currentEditorSaveRef = useRef<
    ((force?: boolean) => Promise<void>) | null
  >(null);

  // Register a save function provided by the TextArea component
  const registerSaveFunction = useCallback(
    (saveFunc: (force?: boolean) => Promise<void>) => {
      currentEditorSaveRef.current = saveFunc;
    },
    []
  );

  // Handle document selection with saving
  const handleSelectDocument = useCallback(
    async (docId: number) => {
      if (activeDocumentId !== docId) {
        // Trigger save on the current document before switching
        if (currentEditorSaveRef.current) {
          try {
            console.log("Saving current document before tab change");
            await currentEditorSaveRef.current(true); // Force save
          } catch (err) {
            console.error("Failed to save document during tab change:", err);
          }
        }

        // Then switch to the new document
        selectDocument(docId);
      }
    },
    [activeDocumentId, selectDocument]
  );

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <div className="bg-gray-100 p-2 border-b text-sm text-gray-500">
          Cargando documentos...
        </div>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner />
        </div>
      </div>
    );
  }

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
      <TabBar
        documents={documents}
        activeDocumentId={activeDocumentId}
        onSelectDocument={handleSelectDocument} // Use our wrapped handler
      />

      <div className="flex-1 overflow-auto bg-white">
        {activeDocument ? (
          <TextArea
            key={activeDocument.id} // Important: key ensures full remount on document change
            document={activeDocument}
            readOnly={false}
            onSave={async (docId, content) => {
              await saveDocument(docId, content); // Discard the boolean result
              // Returns void implicitly
            }}
            registerSaveFunction={registerSaveFunction}
            // Pass these additional props to TextArea
            documentContentCache={documentContentCache}
            fetchDocumentContent={fetchDocumentContent}
            isLoadingContent={isLoadingContent}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            {documents.length > 0
              ? "Seleccione un documento para visualizar"
              : "No hay documentos disponibles para este encuentro"}
          </div>
        )}
      </div>

      {/* Saving indicator */}
      {isSaving && (
        <div className="bg-blue-50 text-blue-600 text-xs p-1 border-t text-center">
          Guardando cambios...
        </div>
      )}
    </div>
  );
};

export default DocumentArea;
